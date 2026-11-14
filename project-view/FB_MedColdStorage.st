(* ==============================================================================
   FUNCTION BLOCK: FB_MedColdStorage
   DESCRIPTION: Encapsulated clinical monitoring block for Medical Cold Storage
                & Cleanroom Ambient Telemetry (Slot 2 Wireless Node).
                Integrates:
                - Medical Refrigerator (Hierarchical fbFridge: FB_MedFridge)
                - Medical Freezer (Hierarchical fbFreezer: FB_MedFreezer)
                - Lab Cleanroom Ambient Temp (20.0°C to 27.0°C Comfort Range)
                - Cleanroom Wireless Diagnostics (Battery, RSSI, Faults, Comm Loss)
                Modbus RTU Slave Slot 2 Holding Registers:
                - Offset 0: Mapped directly to fbFridge.wRawTempX10
                - Offsets 1..7: Shared wireless telemetry & diagnostics
                - Offset 8: Mapped directly to fbFreezer.wRawTempX10
                - Offset 9: Mapped to wRawAmbientTempX10
   ============================================================================== *)
FUNCTION_BLOCK FB_MedColdStorage
VAR_INPUT
    (* --- 10 Modbus Holding Registers (Direct from Bridge Slot 2) --- *)
    wRawFridgeTempX10   : WORD := 16#D8F0;  (* Offset 0: Raw Modbus register (Fridge scaled temp * 10, -9999 = 16#D8F0) *)
    uiRawBatteryMv      : UINT := 3820;     (* Offset 1: Battery health in millivolts *)
    uiRawFaultCode      : UINT := 0;        (* Offset 2: Probe fault code bitmask (bit 0=Fridge, bit 1=Freezer, bit 2=Ambient) *)
    wRawRSSI            : WORD := 16#FFCE;  (* Offset 3: Raw Modbus register (Link margin in dBm, -50 = 16#FFCE) *)
    wRawSeqLow          : WORD := 0;        (* Offset 4: Sequence counter low word *)
    wRawSeqHigh         : WORD := 0;        (* Offset 5: Sequence counter high word *)
    uiRawAgeSec         : UINT := 0;        (* Offset 6: Telemetry age in seconds *)
    wRawStatusFlags     : WORD := 16#0001;  (* Offset 7: Bit 0=Online, Bit 1=LowBatt, Bit 2=CommLoss *)
    wRawFreezerTempX10  : WORD := 16#D8F0;  (* Offset 8: Raw Modbus register (Freezer scaled temp * 10, -9999 = 16#D8F0) *)
    wRawAmbientTempX10  : WORD := 16#D8F0;  (* Offset 9: Raw Modbus register (Ambient scaled temp * 10, -9999 = 16#D8F0) *)

    (* --- Ambient Room Comfort Thresholds --- *)
    rAmbientHighTrip    : REAL := 27.0;     (* Cleanroom upper comfort limit (°C) *)
    rAmbientLowTrip     : REAL := 20.0;     (* Cleanroom lower comfort limit (°C) *)
    rAmbientHysteresis  : REAL := 0.5;      (* Anti-chatter deadband (°C) *)
    tAmbientPickupDelay : TIME := T#5M;     (* 5-minute sustained delay for HVAC drift *)
    tAmbientDropoutDelay: TIME := T#10S;    (* 10-second clean recovery *)

    bIsWireless         : BOOL := TRUE;     (* TRUE = Enable wireless diagnostics *)
    tCommLossTimeout    : TIME := T#60S;    (* Watchdog comms loss alarm threshold *)
END_VAR
VAR_OUTPUT
    (* --- Published Ambient Room Telemetry to SCADA & UI --- *)
    rAmbientTemp        : REAL := -999.0;   (* Cleanroom Ambient Room Temp (°C) *)
    bAmbientAlarm       : BOOL := FALSE;    (* Ambient Room Drift Priority 2 Alarm *)
    bAmbientWarn        : BOOL := FALSE;    (* Ambient Room Drift Warning *)
    bAmbientProbeFault  : BOOL := TRUE;     (* Ambient probe disconnected or shorted *)

    (* --- Shared Wireless Cleanroom Health Diagnostics --- *)
    rBatteryVolts       : REAL := 3.82;     (* Published battery voltage (V) *)
    bLowBattery         : BOOL := FALSE;    (* Low battery warning flag (< 3.4V) *)
    iRSSI               : INT := -50;       (* Published wireless link margin (dBm) *)
    bCommLoss           : BOOL := FALSE;    (* Comms loss watchdog alarm *)
    uiFaultCode         : UINT := 0;        (* Published probe fault reason *)
    uiAgeSec            : UINT := 0;        (* Telemetry age in seconds *)
END_VAR
VAR
    fbFridge            : FB_MedFridge;     (* Hierarchical Medical Refrigerator Subsystem *)
    fbFreezer           : FB_MedFreezer;    (* Hierarchical Medical Freezer Subsystem *)
    fbAmbientAlarmEval  : FB_AnalogAlarm;   (* Cleanroom Ambient Comfort Window Evaluator *)
    iAmbientTempX10     : INT;
    iFreezerTempX10     : INT;
    bFreezerSwapSuspect : BOOL := FALSE;
    uiFreezerFaultIn    : UINT := 0;
    tonOnlineSettle     : TON;              (* Hold CommLoss through initial Modbus settle on boot/reconnect *)
    bLinkOnline         : BOOL := FALSE;    (* Bridge online bit set and watchdog healthy *)
END_VAR
// --- implementation ---
// ==============================================================================
// 1. SHARED WIRELESS CLEANROOM HEALTH & TELEMETRY DECODING
// ==============================================================================
IF bIsWireless THEN
    rBatteryVolts := TO_REAL(uiRawBatteryMv) / 1000.0;
    bLowBattery   := (uiRawBatteryMv < 3400) OR (wRawStatusFlags.1);
    iRSSI         := TO_INT(wRawRSSI);
    uiAgeSec      := uiRawAgeSec;
    uiFaultCode   := uiRawFaultCode;
    (* Require bridge Online bit (Bit 0) + 2s settle before leaving CommLoss
       so scan-1 unpopulated Modbus holding registers (all zeros = 0.0 C)
       cannot falsely prime the thermal vial filter on boot/reload. *)
    bLinkOnline   := wRawStatusFlags.0
        AND (NOT wRawStatusFlags.2)
        AND (uiRawAgeSec < (TIME_TO_UINT(tCommLossTimeout) / 1000));
    tonOnlineSettle(IN := bLinkOnline, PT := T#2S);
    bCommLoss     := NOT tonOnlineSettle.Q;
ELSE
    rBatteryVolts := 0.0;
    bLowBattery   := FALSE;
    iRSSI         := 0;
    bCommLoss     := FALSE;
    uiFaultCode   := 0;
    uiAgeSec      := 0;
    tonOnlineSettle(IN := FALSE);
END_IF;

// ==============================================================================
// 2. MEDICAL REFRIGERATOR (Hierarchical FB_MedFridge Instance)
// ==============================================================================
fbFridge(
    wRawTempX10         := wRawFridgeTempX10,
    uiRawFaultCode      := BOOL_TO_UINT((uiRawFaultCode AND 16#0001) <> 0),
    bCommLoss           := bCommLoss
);

// ==============================================================================
// 3. MEDICAL FREEZER (Hierarchical FB_MedFreezer Instance)
// ==============================================================================
(* Pre-evaluate Ambient fault & check for legacy dynamic-ROM slot shift
   (if Freezer probe drops out, pre-pinned node firmware shifts room Ambient
   >12 C into the Freezer slot while Ambient goes -999 / bit 2). *)
iAmbientTempX10     := TO_INT(wRawAmbientTempX10);
bAmbientProbeFault  := ((uiRawFaultCode AND 16#0004) <> 0) OR (iAmbientTempX10 <= -9000) OR (iAmbientTempX10 >= 9000);
iFreezerTempX10     := TO_INT(wRawFreezerTempX10);
bFreezerSwapSuspect := bAmbientProbeFault AND (iFreezerTempX10 > 120) AND (iFreezerTempX10 < 9000) AND (fbFreezer.rProcessTemp < 5.0);
uiFreezerFaultIn    := BOOL_TO_UINT(((uiRawFaultCode AND 16#0002) <> 0) OR bFreezerSwapSuspect);

fbFreezer(
    wRawTempX10         := wRawFreezerTempX10,
    uiRawFaultCode      := uiFreezerFaultIn,
    bCommLoss           := bCommLoss
);

// ==============================================================================
// 4. CLEANROOM AMBIENT ROOM TEMPERATURE (20.0°C to 27.0°C Comfort Window)
// ==============================================================================
IF bAmbientProbeFault OR bCommLoss THEN
    rAmbientTemp := -999.0;
ELSE
    rAmbientTemp := TO_REAL(iAmbientTempX10) / 10.0;
END_IF;

fbAmbientAlarmEval(
    rVal          := rAmbientTemp,
    bEnableHigh   := NOT (bAmbientProbeFault OR bCommLoss),
    rHighPickup   := rAmbientHighTrip,
    rHighDropout  := rAmbientHighTrip - rAmbientHysteresis,
    bEnableLow    := NOT (bAmbientProbeFault OR bCommLoss),
    rLowPickup    := rAmbientLowTrip,
    rLowDropout   := rAmbientLowTrip + rAmbientHysteresis,
    tPickupDelay  := tAmbientPickupDelay,
    tDropoutDelay := tAmbientDropoutDelay
);
bAmbientAlarm := fbAmbientAlarmEval.bAlarm;
bAmbientWarn  := fbAmbientAlarmEval.bWarn;
END_FUNCTION

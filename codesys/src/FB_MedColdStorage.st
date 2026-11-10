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
    {attribute 'symbol' := 'readwrite'}
    wRawFridgeTempX10   : WORD := 16#D8F0;  (* Offset 0: Raw Modbus register (Fridge scaled temp * 10, -9999 = 16#D8F0) *)
    {attribute 'symbol' := 'readwrite'}
    uiRawBatteryMv      : UINT := 3820;     (* Offset 1: Battery health in millivolts *)
    {attribute 'symbol' := 'readwrite'}
    uiRawFaultCode      : UINT := 0;        (* Offset 2: Probe fault code bitmask (bit 0=Fridge, bit 1=Freezer, bit 2=Ambient) *)
    {attribute 'symbol' := 'readwrite'}
    wRawRSSI            : WORD := 16#FFCE;  (* Offset 3: Raw Modbus register (Link margin in dBm, -50 = 16#FFCE) *)
    {attribute 'symbol' := 'readwrite'}
    wRawSeqLow          : WORD := 0;        (* Offset 4: Sequence counter low word *)
    {attribute 'symbol' := 'readwrite'}
    wRawSeqHigh         : WORD := 0;        (* Offset 5: Sequence counter high word *)
    {attribute 'symbol' := 'readwrite'}
    uiRawAgeSec         : UINT := 0;        (* Offset 6: Telemetry age in seconds *)
    {attribute 'symbol' := 'readwrite'}
    wRawStatusFlags     : WORD := 16#0001;  (* Offset 7: Bit 0=Online, Bit 1=LowBatt, Bit 2=CommLoss *)
    {attribute 'symbol' := 'readwrite'}
    wRawFreezerTempX10  : WORD := 16#D8F0;  (* Offset 8: Raw Modbus register (Freezer scaled temp * 10, -9999 = 16#D8F0) *)
    {attribute 'symbol' := 'readwrite'}
    wRawAmbientTempX10  : WORD := 16#D8F0;  (* Offset 9: Raw Modbus register (Ambient scaled temp * 10, -9999 = 16#D8F0) *)

    (* --- Ambient Room Comfort Thresholds --- *)
    {attribute 'symbol' := 'none'}
    rAmbientHighTrip    : REAL := 27.0;     (* Cleanroom upper comfort limit (°C) *)
    {attribute 'symbol' := 'none'}
    rAmbientLowTrip     : REAL := 20.0;     (* Cleanroom lower comfort limit (°C) *)
    {attribute 'symbol' := 'none'}
    rAmbientHysteresis  : REAL := 0.5;      (* Anti-chatter deadband (°C) *)
    {attribute 'symbol' := 'none'}
    tAmbientPickupDelay : TIME := T#5M;     (* 5-minute sustained delay for HVAC drift *)
    {attribute 'symbol' := 'none'}
    tAmbientDropoutDelay: TIME := T#10S;    (* 10-second clean recovery *)

    {attribute 'symbol' := 'none'}
    bIsWireless         : BOOL := TRUE;     (* TRUE = Enable wireless diagnostics *)
    {attribute 'symbol' := 'none'}
    tCommLossTimeout    : TIME := T#60S;    (* Watchdog comms loss alarm threshold *)
END_VAR
VAR_OUTPUT
    (* --- Published Ambient Room Telemetry to SCADA & UI --- *)
    {attribute 'symbol' := 'read'}
    rAmbientTemp        : REAL := -999.0;   (* Cleanroom Ambient Room Temp (°C) *)
    {attribute 'symbol' := 'read'}
    bAmbientAlarm       : BOOL := FALSE;    (* Ambient Room Drift Priority 2 Alarm *)
    {attribute 'symbol' := 'read'}
    bAmbientWarn        : BOOL := FALSE;    (* Ambient Room Drift Warning *)
    {attribute 'symbol' := 'read'}
    bAmbientProbeFault  : BOOL := TRUE;     (* Ambient probe disconnected or shorted *)

    (* --- Shared Wireless Cleanroom Health Diagnostics --- *)
    {attribute 'symbol' := 'read'}
    rBatteryVolts       : REAL := 3.82;     (* Published battery voltage (V) *)
    {attribute 'symbol' := 'read'}
    bLowBattery         : BOOL := FALSE;    (* Low battery warning flag (< 3.4V) *)
    {attribute 'symbol' := 'read'}
    iRSSI               : INT := -50;       (* Published wireless link margin (dBm) *)
    {attribute 'symbol' := 'read'}
    bCommLoss           : BOOL := FALSE;    (* Comms loss watchdog alarm *)
    {attribute 'symbol' := 'read'}
    uiFaultCode         : UINT := 0;        (* Published probe fault reason *)
    {attribute 'symbol' := 'read'}
    uiAgeSec            : UINT := 0;        (* Telemetry age in seconds *)
END_VAR
VAR
    {attribute 'symbol' := 'read'}
    fbFridge            : FB_MedFridge;     (* Hierarchical Medical Refrigerator Subsystem *)
    {attribute 'symbol' := 'read'}
    fbFreezer           : FB_MedFreezer;    (* Hierarchical Medical Freezer Subsystem *)
    {attribute 'symbol' := 'none'}
    fbAmbientAlarmEval  : FB_AnalogAlarm;   (* Cleanroom Ambient Comfort Window Evaluator *)
    {attribute 'symbol' := 'none'}
    iAmbientTempX10     : INT;
END_VAR

// ==============================================================================
// 1. SHARED WIRELESS CLEANROOM HEALTH & TELEMETRY DECODING
// ==============================================================================
IF bIsWireless THEN
    rBatteryVolts := TO_REAL(uiRawBatteryMv) / 1000.0;
    bLowBattery   := (uiRawBatteryMv < 3400) OR (wRawStatusFlags.1);
    iRSSI         := TO_INT(wRawRSSI);
    uiAgeSec      := uiRawAgeSec;
    uiFaultCode   := uiRawFaultCode;
    bCommLoss     := (uiRawAgeSec >= (TIME_TO_UINT(tCommLossTimeout) / 1000)) OR (wRawStatusFlags.2);
ELSE
    rBatteryVolts := 0.0;
    bLowBattery   := FALSE;
    iRSSI         := 0;
    bCommLoss     := FALSE;
    uiFaultCode   := 0;
    uiAgeSec      := 0;
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
fbFreezer(
    wRawTempX10         := wRawFreezerTempX10,
    uiRawFaultCode      := BOOL_TO_UINT((uiRawFaultCode AND 16#0002) <> 0),
    bCommLoss           := bCommLoss
);

// ==============================================================================
// 4. CLEANROOM AMBIENT ROOM TEMPERATURE (20.0°C to 27.0°C Comfort Window)
// ==============================================================================
iAmbientTempX10 := TO_INT(wRawAmbientTempX10);
bAmbientProbeFault := ((uiRawFaultCode AND 16#0004) <> 0) OR (iAmbientTempX10 <= -9000) OR (iAmbientTempX10 >= 9000);

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

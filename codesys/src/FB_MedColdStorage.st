(* ==============================================================================
   FUNCTION BLOCK: FB_MedColdStorage
   DESCRIPTION: Encapsulated clinical monitoring block for Medical Cold Storage
                & Cleanroom Ambient Telemetry (Slot 2 Wireless Node).
                Integrates:
                - Medical Refrigerator (2.0°C to 8.5°C Dual-Limit Window Alarm)
                - Medical Freezer (< -15.0°C High Excursion Alarm)
                - Lab Cleanroom Ambient Temp (20.0°C to 27.0°C Comfort Range)
                - Cleanroom Wireless Diagnostics (Battery, RSSI, Faults, Comm Loss)
                Directly binds to Modbus RTU Slave Slot 2 (Holding Registers 0..9).
   ============================================================================== *)
FUNCTION_BLOCK FB_MedColdStorage
VAR_INPUT
    (* --- 10 Modbus Holding Registers (Direct from Bridge Slot 2) --- *)
    {attribute 'symbol' := 'readwrite'}
    iRawFridgeTempX10   : INT := -9999;     (* Offset 0: Fridge scaled temp * 10 (35 = +3.5 °C, -9999 = Sentinel) *)
    {attribute 'symbol' := 'readwrite'}
    uiRawBatteryMv      : UINT := 3820;     (* Offset 1: Battery health in millivolts *)
    {attribute 'symbol' := 'readwrite'}
    uiRawFaultCode      : UINT := 0;        (* Offset 2: Probe fault code bitmask (0=OK, 0xFF=Unpopulated) *)
    {attribute 'symbol' := 'readwrite'}
    iRawRSSI            : INT := -50;       (* Offset 3: Wireless link margin (dBm) *)
    {attribute 'symbol' := 'readwrite'}
    wRawSeqLow          : WORD := 0;        (* Offset 4: Sequence counter low word *)
    {attribute 'symbol' := 'readwrite'}
    wRawSeqHigh         : WORD := 0;        (* Offset 5: Sequence counter high word *)
    {attribute 'symbol' := 'readwrite'}
    uiRawAgeSec         : UINT := 0;        (* Offset 6: Telemetry age in seconds *)
    {attribute 'symbol' := 'readwrite'}
    wRawStatusFlags     : WORD := 16#0001;  (* Offset 7: Bit 0=Online, Bit 1=LowBatt, Bit 2=CommLoss *)
    {attribute 'symbol' := 'readwrite'}
    iRawFreezerTempX10  : INT := -9999;     (* Offset 8: Freezer scaled temp * 10 (-180 = -18.0 °C, -9999 = Sentinel) *)
    {attribute 'symbol' := 'readwrite'}
    iRawAmbientTempX10  : INT := -9999;     (* Offset 9: Ambient scaled temp * 10 (250 = +25.0 °C, -9999 = Sentinel) *)

    (* --- Operational Alarm Thresholds & Delays --- *)
    {attribute 'symbol' := 'none'}
    rFridgeHighTrip     : REAL := 8.5;      (* CAP excursion threshold (standard 8.0°C + 0.5 buffer) *)
    {attribute 'symbol' := 'none'}
    rFridgeLowTrip      : REAL := 2.0;      (* Freezing prevention threshold *)
    {attribute 'symbol' := 'none'}
    rFridgeHysteresis   : REAL := 0.5;      (* Anti-chatter deadband (°C) *)
    {attribute 'symbol' := 'none'}
    tFridgePickupDelay  : TIME := T#2M;     (* 2-minute sustained delay to suppress door-opening noise *)
    {attribute 'symbol' := 'none'}
    tFridgeDropoutDelay : TIME := T#10S;    (* 10-second clean recovery required to reset *)

    {attribute 'symbol' := 'none'}
    rFreezerHighTrip    : REAL := -15.0;    (* Freezer warm excursion threshold (°C) *)
    {attribute 'symbol' := 'none'}
    rFreezerHysteresis  : REAL := 1.5;      (* Anti-chatter deadband (°C) *)
    {attribute 'symbol' := 'none'}
    tFreezerPickupDelay : TIME := T#3M;     (* 3-minute sustained delay to suppress defrost cycles *)
    {attribute 'symbol' := 'none'}
    tFreezerDropoutDelay: TIME := T#10S;    (* 10-second clean recovery required to reset *)

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
    (* --- Published Process Temperatures to SCADA & UI --- *)
    {attribute 'symbol' := 'read'}
    rFridgeTemp         : REAL := -999.0;   (* Medical Refrigerator Process Temp (°C) *)
    {attribute 'symbol' := 'read'}
    rFreezerTemp        : REAL := -999.0;   (* Medical Freezer Process Temp (°C) *)
    {attribute 'symbol' := 'read'}
    rAmbientTemp        : REAL := -999.0;   (* Cleanroom Ambient Room Temp (°C) *)

    (* --- Clinical Alarm & Warning Flags --- *)
    {attribute 'symbol' := 'read'}
    bFridgeAlarm        : BOOL := FALSE;    (* Fridge Excursion Priority 2 Alarm *)
    {attribute 'symbol' := 'read'}
    bFridgeWarn         : BOOL := FALSE;    (* Fridge Pre-alarm pickup delay warning *)
    {attribute 'symbol' := 'read'}
    bFridgeProbeFault   : BOOL := TRUE;     (* Fridge probe disconnected or shorted *)

    {attribute 'symbol' := 'read'}
    bFreezerAlarm       : BOOL := FALSE;    (* Freezer Warm Excursion Priority 2 Alarm *)
    {attribute 'symbol' := 'read'}
    bFreezerWarn        : BOOL := FALSE;    (* Freezer Pre-alarm pickup delay warning *)
    {attribute 'symbol' := 'read'}
    bFreezerProbeFault  : BOOL := TRUE;     (* Freezer probe disconnected or shorted *)

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
    {attribute 'symbol' := 'none'}
    fbFridgeAlarmEval   : FB_AnalogAlarm;
    {attribute 'symbol' := 'none'}
    fbFreezerAlarmEval  : FB_AnalogAlarm;
    {attribute 'symbol' := 'none'}
    fbAmbientAlarmEval  : FB_AnalogAlarm;
END_VAR

// ==============================================================================
// 1. HARDWARE HEALTH & TELEMETRY DECODING
// ==============================================================================
IF bIsWireless THEN
    rBatteryVolts := TO_REAL(uiRawBatteryMv) / 1000.0;
    bLowBattery   := (uiRawBatteryMv < 3400) OR (wRawStatusFlags.1);
    iRSSI         := iRawRSSI;
    uiAgeSec      := uiRawAgeSec;
    uiFaultCode   := uiRawFaultCode;

    // Comms loss watchdog if age exceeds threshold or status flag bit 2 is set
    bCommLoss     := (uiRawAgeSec >= (TIME_TO_UINT(tCommLossTimeout) / 1000)) OR (wRawStatusFlags.2);

    // Individual probe faults: reported in bitmask OR sentinel value (<= -9000 or >= 9000)
    bFridgeProbeFault  := ((uiRawFaultCode AND 16#0001) <> 0) OR (iRawFridgeTempX10 <= -9000) OR (iRawFridgeTempX10 >= 9000);
    bFreezerProbeFault := ((uiRawFaultCode AND 16#0002) <> 0) OR (iRawFreezerTempX10 <= -9000) OR (iRawFreezerTempX10 >= 9000);
    bAmbientProbeFault := ((uiRawFaultCode AND 16#0004) <> 0) OR (iRawAmbientTempX10 <= -9000) OR (iRawAmbientTempX10 >= 9000);
ELSE
    rBatteryVolts      := 0.0;
    bLowBattery        := FALSE;
    iRSSI              := 0;
    bCommLoss          := FALSE;
    uiFaultCode        := 0;
    uiAgeSec           := 0;
    bFridgeProbeFault  := (iRawFridgeTempX10 <= -9000) OR (iRawFridgeTempX10 >= 9000);
    bFreezerProbeFault := (iRawFreezerTempX10 <= -9000) OR (iRawFreezerTempX10 >= 9000);
    bAmbientProbeFault := (iRawAmbientTempX10 <= -9000) OR (iRawAmbientTempX10 >= 9000);
END_IF;

// ==============================================================================
// 2. PROCESS TEMPERATURE SCALING & SENTINEL MAPPING
// ==============================================================================
IF bFridgeProbeFault OR bCommLoss THEN
    rFridgeTemp := -999.0;
ELSE
    rFridgeTemp := TO_REAL(iRawFridgeTempX10) / 10.0;
END_IF;

IF bFreezerProbeFault OR bCommLoss THEN
    rFreezerTemp := -999.0;
ELSE
    rFreezerTemp := TO_REAL(iRawFreezerTempX10) / 10.0;
END_IF;

IF bAmbientProbeFault OR bCommLoss THEN
    rAmbientTemp := -999.0;
ELSE
    rAmbientTemp := TO_REAL(iRawAmbientTempX10) / 10.0;
END_IF;

// ==============================================================================
// 3. CLINICAL ALARM EVALUATION
// ==============================================================================

// --- A. Medical Refrigerator Dual-Limit Window Alarm (2.0°C to 8.5°C) ---
fbFridgeAlarmEval(
    rVal          := rFridgeTemp,
    bEnableHigh   := NOT (bFridgeProbeFault OR bCommLoss),
    rHighPickup   := rFridgeHighTrip,
    rHighDropout  := rFridgeHighTrip - rFridgeHysteresis,
    bEnableLow    := NOT (bFridgeProbeFault OR bCommLoss),
    rLowPickup    := rFridgeLowTrip,
    rLowDropout   := rFridgeLowTrip + rFridgeHysteresis,
    tPickupDelay  := tFridgePickupDelay,
    tDropoutDelay := tFridgeDropoutDelay
);
bFridgeAlarm := fbFridgeAlarmEval.bAlarm;
bFridgeWarn  := fbFridgeAlarmEval.bWarn;

// --- B. Medical Freezer High Threshold Alarm (< -15.0°C) ---
fbFreezerAlarmEval(
    rVal          := rFreezerTemp,
    bEnableHigh   := NOT (bFreezerProbeFault OR bCommLoss),
    rHighPickup   := rFreezerHighTrip,
    rHighDropout  := rFreezerHighTrip - rFreezerHysteresis,
    bEnableLow    := FALSE,
    tPickupDelay  := tFreezerPickupDelay,
    tDropoutDelay := tFreezerDropoutDelay
);
bFreezerAlarm := fbFreezerAlarmEval.bAlarm;
bFreezerWarn  := fbFreezerAlarmEval.bWarn;

// --- C. Cleanroom Ambient Room Temperature Comfort Alarm (20.0°C to 27.0°C) ---
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


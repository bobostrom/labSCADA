(* ==============================================================================
   FUNCTION BLOCK: FB_MedFridge
   DESCRIPTION: Encapsulated clinical monitoring block for Medical Refrigerators
                (embryo media, medications, specimens).
                - Scaled raw integer input (iRawTempX10 / 10.0 -> °C)
                - Dual-limit Window Alarm (2.0°C to 8.5°C) with debounced pickup
                - Clinical fault supervision (Open circuit, wiring short, comms loss)
                - Temperature excursion alarm gated off during hardware faults
                - Wireless cleanroom health diagnostics (Battery, RSSI, Watchdog, Faults)
   ============================================================================== *)
FUNCTION_BLOCK FB_MedFridge
VAR_INPUT
    {attribute 'symbol' := 'readwrite'}
    iRawTempX10         : INT := -9999;     (* Raw scaled temp * 10 (35 = +3.5 °C, -9999 = Sentinel / Disconnected) *)
    {attribute 'symbol' := 'none'}
    rHighTrip           : REAL := 8.5;      (* CAP excursion threshold (standard 8.0°C + 0.5 buffer) *)
    {attribute 'symbol' := 'none'}
    rLowTrip            : REAL := 2.0;      (* Freezing prevention threshold *)
    {attribute 'symbol' := 'none'}
    rHysteresis         : REAL := 0.5;      (* Anti-chatter deadband (°C) *)
    {attribute 'symbol' := 'none'}
    tPickupDelay        : TIME := T#2M;     (* 2-minute sustained delay to suppress door-opening noise *)
    {attribute 'symbol' := 'none'}
    tDropoutDelay       : TIME := T#10S;    (* 10-second clean recovery required to reset *)

    (* --- Wireless Telemetry Inputs (Direct from Modbus Bridge Slot 2) --- *)
    {attribute 'symbol' := 'readwrite'}
    uiRawBatteryMv      : UINT := 3820;     (* Battery health in millivolts *)
    {attribute 'symbol' := 'readwrite'}
    iRawRSSI            : INT := -50;       (* Link RSSI in dBm *)
    {attribute 'symbol' := 'readwrite'}
    uiRawFaultCode      : UINT := 0;        (* Probe fault code: 0=OK, 0xFF=Unpopulated *)
    {attribute 'symbol' := 'readwrite'}
    uiRawAgeSec         : UINT := 0;        (* Seconds since last burst packet *)
    {attribute 'symbol' := 'readwrite'}
    wRawStatusFlags     : WORD := 16#0001;  (* Bit 0=Online, Bit 1=LowBatt, Bit 2=CommLoss *)
    {attribute 'symbol' := 'none'}
    bIsWireless         : BOOL := TRUE;     (* TRUE = Enable wireless diagnostics *)
    {attribute 'symbol' := 'none'}
    tCommLossTimeout    : TIME := T#60S;    (* Watchdog comms loss alarm threshold *)
END_VAR
VAR_OUTPUT
    {attribute 'symbol' := 'read'}
    rProcessTemp        : REAL := -999.0;   (* Published process temperature to SCADA & DB *)
    {attribute 'symbol' := 'read'}
    bAlarm              : BOOL := FALSE;    (* Priority 2 Emergency Alarm flag *)
    {attribute 'symbol' := 'read'}
    bWarn               : BOOL := FALSE;    (* Pre-alarm pickup delay warning flag *)
    {attribute 'symbol' := 'read'}
    rBatteryVolts       : REAL := 3.82;     (* Published battery voltage (V) *)
    {attribute 'symbol' := 'read'}
    bLowBattery         : BOOL := FALSE;    (* Low battery warning flag (< 3.4V) *)
    {attribute 'symbol' := 'read'}
    iRSSI               : INT := -50;       (* Published wireless link margin (dBm) *)
    {attribute 'symbol' := 'read'}
    bCommLoss           : BOOL := FALSE;    (* Comms loss watchdog alarm *)
    {attribute 'symbol' := 'read'}
    bProbeFault         : BOOL := TRUE;     (* Physical probe disconnected or shorted *)
    {attribute 'symbol' := 'read'}
    uiFaultCode         : UINT := 0;        (* Published probe fault reason *)
    {attribute 'symbol' := 'read'}
    uiAgeSec            : UINT := 0;        (* Telemetry age in seconds *)
END_VAR
VAR
    {attribute 'symbol' := 'none'}
    fbAlarmEval         : FB_AnalogAlarm;
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

    // Probe fault if hardware reported fault (0xFF) or value is sentinel (-999.9 °C)
    bProbeFault   := (uiRawFaultCode <> 0) OR (iRawTempX10 <= -9000);
    bCommLoss     := (uiRawAgeSec >= 60) OR (wRawStatusFlags.2);
END_IF;

// ==============================================================================
// 2. PROCESS TEMPERATURE SCALING
// ==============================================================================
rProcessTemp := TO_REAL(iRawTempX10) / 10.0;

// ==============================================================================
// 3. CLINICAL ALARM EVALUATION (Dual-Limit Window Alarm)
// ==============================================================================
fbAlarmEval(
    rVal          := rProcessTemp,
    bEnableHigh   := NOT (bIsWireless AND (bProbeFault OR bCommLoss)),
    rHighPickup   := rHighTrip,
    rHighDropout  := rHighTrip - rHysteresis,
    bEnableLow    := NOT (bIsWireless AND (bProbeFault OR bCommLoss)),
    rLowPickup    := rLowTrip,
    rLowDropout   := rLowTrip + rHysteresis,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

bAlarm     := fbAlarmEval.bAlarm;
bWarn      := fbAlarmEval.bWarn;

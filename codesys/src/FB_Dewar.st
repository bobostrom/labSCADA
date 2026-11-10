(* ==============================================================================
   FUNCTION BLOCK: FB_Dewar
   DESCRIPTION: Encapsulated clinical monitoring block for Liquid Nitrogen (LN2)
                cryogenic storage vessels (dewars / freezers).
                - Scaled raw integer input (iRawTempX10 / 10.0 -> °C)
                - High threshold alarm with hysteresis & debounced pickup timing
                - Clinical fault supervision (Open circuit, wiring short, comms loss)
                - High-temperature excursion alarm gated off during hardware faults
                - Wireless cleanroom health diagnostics (Battery, RSSI, Watchdog, Faults)
   ============================================================================== *)
FUNCTION_BLOCK FB_Dewar
VAR_INPUT
    (* --- Operational Alarm Thresholds & Delays --- *)
    {attribute 'symbol' := 'none'}
    rHighTrip           : REAL := -135.0;   (* Critical specimen danger limit (°C) *)
    {attribute 'symbol' := 'none'}
    rHysteresis         : REAL := 5.0;      (* Reset deadband (°C) *)
    {attribute 'symbol' := 'none'}
    tPickupDelay        : TIME := T#30S;    (* Sustained warm excursion required to trip *)
    {attribute 'symbol' := 'none'}
    tDropoutDelay       : TIME := T#10S;    (* Clean fill required to reset *)

    (* --- 8 Modbus Holding Registers (Direct from Bridge Slot 1) --- *)
    {attribute 'symbol' := 'readwrite'}
    wRawTempX10         : WORD := 16#D8F0;  (* Offset 0: Dewar scaled temp * 10 (-1954 = -195.4 °C, -9999 = Sentinel) *)
    {attribute 'symbol' := 'readwrite'}
    uiRawBatteryMv      : UINT := 3850;     (* Offset 1: Battery health in millivolts *)
    {attribute 'symbol' := 'readwrite'}
    uiRawFaultCode      : UINT := 0;        (* Offset 2: Probe fault (0=OK, 1=Open, 2=GND, 3=VCC, 4=Hardware Error) *)
    {attribute 'symbol' := 'readwrite'}
    wRawRSSI            : WORD := 16#FFCE;  (* Offset 3: Wireless link margin in dBm (-50 = 16#FFCE) *)
    {attribute 'symbol' := 'readwrite'}
    wRawSeqLow          : WORD := 0;        (* Offset 4: Sequence counter low word *)
    {attribute 'symbol' := 'readwrite'}
    wRawSeqHigh         : WORD := 0;        (* Offset 5: Sequence counter high word *)
    {attribute 'symbol' := 'readwrite'}
    uiRawAgeSec         : UINT := 0;        (* Offset 6: Telemetry age in seconds *)
    {attribute 'symbol' := 'readwrite'}
    wRawStatusFlags     : WORD := 16#0001;  (* Offset 7: Bit 0=Online, Bit 1=LowBatt, Bit 2=CommLoss *)
    {attribute 'symbol' := 'none'}
    bIsWireless         : BOOL := TRUE;     (* TRUE = Enable wireless diagnostics *)
    {attribute 'symbol' := 'none'}
    tCommLossTimeout    : TIME := T#60S;    (* Watchdog comms loss alarm threshold *)
END_VAR
VAR_OUTPUT
    {attribute 'symbol' := 'read'}
    rProcessTemp        : REAL := -999.0;   (* Published process temperature to SCADA (°C) *)
    {attribute 'symbol' := 'read'}
    bAlarm              : BOOL := FALSE;    (* Priority 2 Emergency Temperature Alarm flag *)
    {attribute 'symbol' := 'read'}
    bWarn               : BOOL := FALSE;    (* Pre-alarm pickup delay warning flag *)
    {attribute 'symbol' := 'read'}
    rBatteryVolts       : REAL := 3.85;     (* Published battery voltage (V) *)
    {attribute 'symbol' := 'read'}
    bLowBattery         : BOOL := FALSE;    (* Low battery warning flag (< 3.4V) *)
    {attribute 'symbol' := 'read'}
    iRSSI               : INT := -50;       (* Published wireless link margin (dBm) *)
    {attribute 'symbol' := 'read'}
    bCommLoss           : BOOL := FALSE;    (* Comms loss watchdog alarm *)
    {attribute 'symbol' := 'read'}
    bProbeFault         : BOOL := TRUE;     (* Physical probe disconnected or shorted (defaults TRUE on cold boot) *)
    {attribute 'symbol' := 'read'}
    uiFaultCode         : UINT := 0;        (* Published probe fault reason (0=OK, 1=Open, 2=GND, 3=VCC) *)
    {attribute 'symbol' := 'read'}
    uiAgeSec            : UINT := 0;        (* Telemetry age in seconds *)
END_VAR
VAR
    {attribute 'symbol' := 'none'}
    iTempX10            : INT;
    {attribute 'symbol' := 'none'}
    fbAlarmEval         : FB_AnalogAlarm;
END_VAR

// ==============================================================================
// 1. HARDWARE HEALTH & TELEMETRY DECODING
// ==============================================================================
// Explicitly cast Modbus unsigned WORD inputs to signed two's complement INT
iTempX10 := TO_INT(wRawTempX10);

IF bIsWireless THEN
    rBatteryVolts := TO_REAL(uiRawBatteryMv) / 1000.0;
    bLowBattery   := (uiRawBatteryMv < 3400) OR (wRawStatusFlags.1);
    iRSSI         := TO_INT(wRawRSSI);
    uiAgeSec      := uiRawAgeSec;
    uiFaultCode   := uiRawFaultCode;

    // Probe fault if hardware reported fault code or value is sentinel (<= -273°C or >= 900°C)
    bProbeFault   := (uiRawFaultCode <> 0) OR (iTempX10 <= -2730) OR (iTempX10 >= 9000);

    // Watchdog comms loss if bridge flagged or age exceeds timeout
    bCommLoss     := (wRawStatusFlags.2) OR (uiRawAgeSec > (TIME_TO_UINT(tCommLossTimeout) / 1000));
ELSE
    rBatteryVolts := 0.0;
    bLowBattery   := FALSE;
    iRSSI         := 0;
    bCommLoss     := FALSE;
    uiFaultCode   := 0;
    bProbeFault   := (iTempX10 <= -2730) OR (iTempX10 >= 9000);
    uiAgeSec      := 0;
END_IF;

// ==============================================================================
// 2. TEMPERATURE SENTINEL MAPPING
// ==============================================================================
// If probe is faulted or comms lost, output standard invalid sentinel (-999.0 °C)
IF bProbeFault OR bCommLoss THEN
    rProcessTemp := -999.0;
ELSE
    rProcessTemp := TO_REAL(iTempX10) / 10.0;
END_IF;

// ==============================================================================
// 3. CLINICAL ALARM EVALUATION (Pickup / Dropout & Hysteresis)
// ==============================================================================
// Thermal excursion alarms are only evaluated when sensor data is valid
fbAlarmEval(
    rVal          := rProcessTemp,
    bEnableHigh   := NOT (bProbeFault OR bCommLoss),
    rHighPickup   := rHighTrip,
    rHighDropout  := rHighTrip - rHysteresis,
    bEnableLow    := FALSE,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

bAlarm     := fbAlarmEval.bAlarm;
bWarn      := fbAlarmEval.bWarn;
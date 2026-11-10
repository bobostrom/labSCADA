(* ==============================================================================
   FUNCTION BLOCK: FB_MedFridge
   DESCRIPTION: Encapsulated clinical monitoring block for Medical Refrigerators
                (embryo media, medications, specimens).
                - Scaled raw integer input (wRawTempX10 / 10.0 -> °C)
                - Dual-limit Window Alarm (2.0°C to 8.5°C) with debounced pickup
                - Clinical fault supervision (Open circuit, wiring short, comms loss)
                - Temperature excursion alarm gated off during hardware faults
   ============================================================================== *)
FUNCTION_BLOCK FB_MedFridge
VAR_INPUT
    {attribute 'symbol' := 'readwrite'}
    wRawTempX10         : WORD := 16#D8F0;  (* Raw Modbus register (Fridge scaled temp * 10, -9999 = 16#D8F0) *)
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
    {attribute 'symbol' := 'none'}
    uiRawFaultCode      : UINT := 0;        (* Probe fault code: 0=OK, 0xFF=Unpopulated *)
    {attribute 'symbol' := 'none'}
    bCommLoss           : BOOL := FALSE;    (* Watchdog comms loss flag *)
END_VAR
VAR_OUTPUT
    {attribute 'symbol' := 'read'}
    rProcessTemp        : REAL := -999.0;   (* Published process temperature to SCADA & DB *)
    {attribute 'symbol' := 'read'}
    bAlarm              : BOOL := FALSE;    (* Priority 2 Emergency Alarm flag *)
    {attribute 'symbol' := 'read'}
    bWarn               : BOOL := FALSE;    (* Pre-alarm pickup delay warning flag *)
    {attribute 'symbol' := 'read'}
    bProbeFault         : BOOL := TRUE;     (* Physical probe disconnected or shorted *)
END_VAR
VAR
    {attribute 'symbol' := 'none'}
    iTempX10            : INT;
    {attribute 'symbol' := 'none'}
    fbAlarmEval         : FB_AnalogAlarm;
END_VAR

// ==============================================================================
// 1. HARDWARE HEALTH & PROCESS TEMPERATURE SCALING
// ==============================================================================
iTempX10    := TO_INT(wRawTempX10);
bProbeFault := (uiRawFaultCode <> 0) OR (iTempX10 <= -9000) OR (iTempX10 >= 9000);

IF bProbeFault OR bCommLoss THEN
    rProcessTemp := -999.0;
ELSE
    rProcessTemp := TO_REAL(iTempX10) / 10.0;
END_IF;

// ==============================================================================
// 2. CLINICAL ALARM EVALUATION (Dual-Limit Window Alarm)
// ==============================================================================
fbAlarmEval(
    rVal          := rProcessTemp,
    bEnableHigh   := NOT (bProbeFault OR bCommLoss),
    rHighPickup   := rHighTrip,
    rHighDropout  := rHighTrip - rHysteresis,
    bEnableLow    := NOT (bProbeFault OR bCommLoss),
    rLowPickup    := rLowTrip,
    rLowDropout   := rLowTrip + rHysteresis,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

bAlarm := fbAlarmEval.bAlarm;
bWarn  := fbAlarmEval.bWarn;

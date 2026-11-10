(* ==============================================================================
   FUNCTION BLOCK: FB_MedFreezer
   DESCRIPTION: Encapsulated clinical monitoring block for Medical Freezers
                (-20°C sperm/media or -80°C ultra-low freezers).
                - Scaled raw integer input (iRawTempX10 / 10.0 -> °C)
                - High temperature threshold alarm with debounce pickup
                - Clinical fault supervision (Open circuit, wiring short, comms loss)
                - Temperature excursion alarm gated off during hardware faults
   ============================================================================== *)
FUNCTION_BLOCK FB_MedFreezer
VAR_INPUT
    {attribute 'symbol' := 'readwrite'}
    wRawTempX10         : WORD := 16#D8F0;  (* Offset 0: Raw Modbus register (-9999 = 16#D8F0 Sentinel / Disconnected) *)
    {attribute 'symbol' := 'none'}
    rHighTrip           : REAL := -10.0;    (* Medications/consumables warm alarm threshold (°C) per USP <1079> *)
    {attribute 'symbol' := 'none'}
    rHysteresis         : REAL := 0.5;      (* Anti-chatter deadband (°C) - resets at -10.5°C *)
    {attribute 'symbol' := 'none'}
    tPickupDelay        : TIME := T#3M;     (* 3-minute sustained delay to suppress defrost cycles *)
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
    bProbeFault         : BOOL := TRUE;     (* Probe disconnected or hardware fault *)
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
iTempX10     := TO_INT(wRawTempX10);
bProbeFault  := (uiRawFaultCode <> 0) OR (iTempX10 <= -9000) OR (iTempX10 >= 9000);

IF bProbeFault OR bCommLoss THEN
    rProcessTemp := -999.0;
ELSE
    rProcessTemp := TO_REAL(iTempX10) / 10.0;
END_IF;

// ==============================================================================
// 2. CLINICAL ALARM EVALUATION
// ==============================================================================
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


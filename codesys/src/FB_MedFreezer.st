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
    iRawTempX10         : INT := -9999;     (* Raw scaled temp * 10 (-180 = -18.0 °C, -9999 = Sentinel / Disconnected) *)
    {attribute 'symbol' := 'none'}
    rHighTrip           : REAL := -15.0;    (* Warm alarm threshold (°C) *)
    {attribute 'symbol' := 'none'}
    rHysteresis         : REAL := 1.5;      (* Anti-chatter deadband (°C) *)
    {attribute 'symbol' := 'none'}
    tPickupDelay        : TIME := T#3M;     (* 3-minute sustained delay to suppress defrost cycles *)
    {attribute 'symbol' := 'none'}
    tDropoutDelay       : TIME := T#10S;    (* 10-second clean recovery required to reset *)
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
    fbAlarmEval         : FB_AnalogAlarm;
END_VAR

// ==============================================================================
// 1. HARDWARE HEALTH & PROCESS TEMPERATURE SCALING
// ==============================================================================
bProbeFault  := (iRawTempX10 <= -9000);
rProcessTemp := TO_REAL(iRawTempX10) / 10.0;

// ==============================================================================
// 2. CLINICAL ALARM EVALUATION
// ==============================================================================
fbAlarmEval(
    rVal          := rProcessTemp,
    bEnableHigh   := NOT bProbeFault,
    rHighPickup   := rHighTrip,
    rHighDropout  := rHighTrip - rHysteresis,
    bEnableLow    := FALSE,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

bAlarm     := fbAlarmEval.bAlarm;
bWarn      := fbAlarmEval.bWarn;


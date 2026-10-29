(* ==============================================================================
   FUNCTION BLOCK: FB_MedFridge
   DESCRIPTION: Encapsulated clinical monitoring block for Medical Refrigerators
                (embryo media, medications, specimens).
                Features:
                - Granular per-device Virtual Simulation Mode (bSimMode)
                - Granular fault injection (bForceExcursion)
                - Dual-limit Window Alarm (2.0°C to 8.0°C) with debounced pickup
                - Direct physical terminal binding (rRawTemp)
   ============================================================================== *)
FUNCTION_BLOCK FB_MedFridge
VAR_INPUT
    {attribute 'symbol' := 'none'}
    rRawTemp            : REAL := 3.5;      (* Physical sensor terminal value *)
    {attribute 'symbol' := 'none'}
    bSimMode            : BOOL := FALSE;    (* TRUE = Ignore terminal, use realistic compressor physics *)
    {attribute 'symbol' := 'none'}
    rNominalTemp        : REAL := 3.5;      (* Target operating point (°C) *)
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
END_VAR
VAR_OUTPUT
    {attribute 'symbol' := 'read'}
    rProcessTemp        : REAL;             (* Published process temperature to SCADA & DB *)
    {attribute 'symbol' := 'read'}
    bAlarm              : BOOL := FALSE;    (* Priority 2 Emergency Alarm flag *)
    {attribute 'symbol' := 'read'}
    bWarn               : BOOL := FALSE;    (* Pre-alarm pickup delay warning flag *)
    {attribute 'symbol' := 'none'}
    bHighTrip           : BOOL := FALSE;
    {attribute 'symbol' := 'none'}
    bLowTrip            : BOOL := FALSE;
    {attribute 'symbol' := 'none'}
    tElapsedPU          : TIME := T#0S;
    {attribute 'symbol' := 'none'}
    tElapsedDO          : TIME := T#0S;
END_VAR
VAR
    {attribute 'symbol' := 'readwrite'}
    bForceExcursion     : BOOL := FALSE;    (* Injects warm excursion above 8.5°C in sim mode *)
    {attribute 'symbol' := 'none'}
    fbAlarmEval         : FB_AnalogAlarm;
    {attribute 'symbol' := 'none'}
    tonSimTick          : TON;
    {attribute 'symbol' := 'none'}
    iAngle              : INT := 0;
END_VAR

// 1. DYNAMICS SIMULATION GENERATOR (Runs if bSimMode is active)
IF bSimMode THEN
    tonSimTick(IN := NOT tonSimTick.Q, PT := T#1S);
    IF tonSimTick.Q THEN
        iAngle := (iAngle + 2) MOD 360;
    END_IF;

    IF bForceExcursion THEN
        // Door ajar or cooling failure: warms up to 9.5 °C
        rProcessTemp := 9.5 + 0.4 * COS(TO_REAL(iAngle) * 0.08);
    ELSE
        // Healthy refrigeration cycle: cycling gently between 2.8°C and 4.2°C
        rProcessTemp := rNominalTemp + 0.6 * COS(TO_REAL(iAngle) * 0.05);
    END_IF;
ELSE
    // Read live physical probe from WAGO I/O terminal
    rProcessTemp := rRawTemp;
END_IF;

// 2. CLINICAL ALARM EVALUATION (Dual-Limit Window Alarm)
fbAlarmEval(
    rVal          := rProcessTemp,
    bEnableHigh   := TRUE,
    rHighPickup   := rHighTrip,
    rHighDropout  := rHighTrip - rHysteresis,
    bEnableLow    := TRUE,
    rLowPickup    := rLowTrip,
    rLowDropout   := rLowTrip + rHysteresis,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

bAlarm     := fbAlarmEval.bAlarm;
bWarn      := fbAlarmEval.bPickup AND NOT fbAlarmEval.bAlarm;
bHighTrip  := fbAlarmEval.bHighTrip;
bLowTrip   := fbAlarmEval.bLowTrip;
tElapsedPU := fbAlarmEval.tElapsedPU;
tElapsedDO := fbAlarmEval.tElapsedDO;

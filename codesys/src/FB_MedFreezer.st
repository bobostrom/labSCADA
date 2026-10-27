(* ==============================================================================
   FUNCTION BLOCK: FB_MedFreezer
   DESCRIPTION: Encapsulated clinical monitoring block for Medical Freezers
                (-20°C sperm/media or -80°C ultra-low freezers).
                Features:
                - Granular per-device Virtual Simulation Mode (bSimMode)
                - Granular fault injection (bForceExcursion)
                - High temperature threshold alarm with debounce pickup
                - Direct physical terminal binding (rRawTemp)
   ============================================================================== *)
FUNCTION_BLOCK FB_MedFreezer
VAR_INPUT
    rRawTemp            : REAL := -20.0;    (* Physical sensor terminal value *)
    bSimMode            : BOOL := FALSE;    (* TRUE = Ignore terminal, use realistic compressor physics *)
    bForceExcursion     : BOOL := FALSE;    (* Injects warm excursion above -15.0°C *)
    rNominalTemp        : REAL := -20.0;    (* Target operating point (°C) *)
    rHighTrip           : REAL := -15.0;    (* Warm alarm threshold (°C) *)
    rHysteresis         : REAL := 1.5;      (* Anti-chatter deadband (°C) *)
    tPickupDelay        : TIME := T#3M;     (* 3-minute sustained delay to suppress defrost cycles *)
    tDropoutDelay       : TIME := T#10S;    (* 10-second clean recovery required to reset *)
END_VAR
VAR_OUTPUT
    rProcessTemp        : REAL;             (* Published process temperature to SCADA & DB *)
    bAlarm              : BOOL := FALSE;    (* Priority 2 Emergency Alarm flag *)
    bWarn               : BOOL := FALSE;    (* Pre-alarm pickup delay warning flag *)
    bHighTrip           : BOOL := FALSE;
    tElapsedPU          : TIME := T#0S;
    tElapsedDO          : TIME := T#0S;
END_VAR
VAR
    fbAlarmEval         : FB_AnalogAlarm;
    tonSimTick          : TON;
    iAngle              : INT := 0;
END_VAR

// 1. DYNAMICS SIMULATION GENERATOR (Runs if bSimMode is active)
IF bSimMode THEN
    tonSimTick(IN := NOT tonSimTick.Q, PT := T#1S);
    IF tonSimTick.Q THEN
        iAngle := (iAngle + 2) MOD 360;
    END_IF;

    IF bForceExcursion THEN
        // Compressor failure or defrost stall: warms up to -12.0 °C
        rProcessTemp := -12.0 + 0.6 * SIN(TO_REAL(iAngle) * 0.06);
    ELSE
        // Healthy freezer compressor cycle: cycling gently around -20.0 °C
        rProcessTemp := rNominalTemp + 0.6 * SIN(TO_REAL(iAngle) * 0.06);
    END_IF;
ELSE
    // Read live physical probe from WAGO I/O terminal
    rProcessTemp := rRawTemp;
END_IF;

// 2. CLINICAL ALARM EVALUATION
fbAlarmEval(
    rVal          := rProcessTemp,
    bEnableHigh   := TRUE,
    rHighPickup   := rHighTrip,
    rHighDropout  := rHighTrip - rHysteresis,
    bEnableLow    := FALSE,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

bAlarm     := fbAlarmEval.bAlarm;
bWarn      := fbAlarmEval.bPickup AND NOT fbAlarmEval.bAlarm;
bHighTrip  := fbAlarmEval.bHighTrip;
tElapsedPU := fbAlarmEval.tElapsedPU;
tElapsedDO := fbAlarmEval.tElapsedDO;

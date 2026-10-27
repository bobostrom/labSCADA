(* ==============================================================================
   FUNCTION BLOCK: FB_Dewar
   DESCRIPTION: Encapsulated clinical monitoring block for Liquid Nitrogen (LN2)
                cryogenic storage vessels (dewars / freezers).
                Features:
                - Granular per-device Virtual Simulation Mode (bSimMode)
                - Granular fault injection (bForceExcursion)
                - High threshold alarm with hysteresis & debounced pickup timing
                - Direct physical terminal binding (rRawTemp)
   ============================================================================== *)
FUNCTION_BLOCK FB_Dewar
VAR_INPUT
    rRawTemp            : REAL := -150.0;   (* Physical sensor terminal value (e.g. WAGO 750-461) *)
    bSimMode            : BOOL := FALSE;    (* TRUE = Ignore terminal, use realistic virtual physics *)
    bForceExcursion     : BOOL := FALSE;    (* Injects critical excursion above -135°C in sim mode *)
    rNominalTemp        : REAL := -150.0;   (* Typical vapor phase operating temperature (°C) *)
    rHighTrip           : REAL := -135.0;   (* Critical specimen danger limit (°C) *)
    rHysteresis         : REAL := 5.0;      (* Reset deadband (°C) *)
    tPickupDelay        : TIME := T#30S;    (* Sustained warm excursion required to trip *)
    tDropoutDelay       : TIME := T#10S;    (* Clean fill required to reset *)
END_VAR
VAR_OUTPUT
    rProcessTemp        : REAL;             (* Published process temperature to SCADA & DB *)
    bAlarm              : BOOL := FALSE;    (* Priority 2 Emergency Alarm flag *)
    bWarn               : BOOL := FALSE;    (* Pre-alarm pickup delay warning flag *)
    bHighTrip           : BOOL := FALSE;    (* Instantaneous excursion indicator *)
    tElapsedPU          : TIME := T#0S;     (* Time excursion has persisted *)
    tElapsedDO          : TIME := T#0S;     (* Time recovery has persisted *)
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
        iAngle := (iAngle + 3) MOD 360;
    END_IF;

    IF bForceExcursion THEN
        // Boiling off / vacuum loss: temperature rises to -125.0 °C
        rProcessTemp := -125.0 + 1.2 * COS(TO_REAL(iAngle) * 0.05);
    ELSE
        // Healthy cryogenic vapor phase: smooth breathing around nominal
        rProcessTemp := rNominalTemp + 0.8 * SIN(TO_REAL(iAngle) * 0.04);
    END_IF;
ELSE
    // Read live physical probe from WAGO I/O terminal
    rProcessTemp := rRawTemp;
END_IF;

// 2. CLINICAL ALARM EVALUATION (Pickup / Dropout & Hysteresis)
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

END_FUNCTION_BLOCK

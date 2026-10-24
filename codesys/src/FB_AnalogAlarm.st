(* ==============================================================================
   FUNCTION BLOCK: FB_AnalogAlarm
   DESCRIPTION: IEC 61131-3 Structured Text implementation of an industrial
                analog alarm monitor with pickup/dropout hysteresis deadbands
                and sustained excursion / reset timers.

                Supports:
                - High Alarm trip / dropout (e.g. Fridge High > 8.0°C, reset < 7.5°C)
                - Low Alarm trip / dropout (e.g. Fridge Low < 2.0°C, reset > 2.5°C)
                - Window Alarm (High + Low simultaneously enabled)
                - Configurable Pickup Delay (prevents trips on brief door opens or noise)
                - Configurable Dropout Delay (anti-chatter filter on recovery)
                - Diagnostic Trip Outputs (HighTrip, LowTrip, Elapsed Timers)
   ============================================================================== *)
FUNCTION_BLOCK FB_AnalogAlarm
VAR_INPUT
    rVal            : REAL;             (* Analog process value to monitor (e.g. Temperature) *)
    bEnableHigh     : BOOL := TRUE;     (* Enable High Alarm monitoring *)
    rHighPickup     : REAL := 0.0;      (* High trip pickup threshold *)
    rHighDropout    : REAL := 0.0;      (* High trip reset threshold (or leave 0.0 and use rHysteresis) *)
    bEnableLow      : BOOL := FALSE;    (* Enable Low Alarm monitoring *)
    rLowPickup      : REAL := 0.0;      (* Low trip pickup threshold *)
    rLowDropout     : REAL := 0.0;      (* Low trip reset threshold (or leave 0.0 and use rHysteresis) *)
    rHysteresis     : REAL := 0.0;      (* Optional deadband offset applied if Dropout not explicitly set *)
    tPickupDelay    : TIME := T#0S;     (* Time excursion must persist before alarm asserts *)
    tDropoutDelay   : TIME := T#0S;     (* Time normal state must persist before alarm clears *)
END_VAR
VAR_OUTPUT
    bAlarm          : BOOL := FALSE;    (* Filtered alarm output (Active Alarm) *)
    bPickup         : BOOL := FALSE;    (* Instantaneous pickup status (pre-timer) *)
    bHighTrip       : BOOL := FALSE;    (* TRUE if High Alarm condition caused/maintains trip *)
    bLowTrip        : BOOL := FALSE;    (* TRUE if Low Alarm condition caused/maintains trip *)
    tElapsedPU      : TIME := T#0S;     (* Current elapsed pickup timer *)
    tElapsedDO      : TIME := T#0S;     (* Current elapsed dropout timer *)
END_VAR
VAR
    rEffHighDO      : REAL;
    rEffLowDO       : REAL;
    bHighCondition  : BOOL := FALSE;
    bLowCondition   : BOOL := FALSE;
    fbTimer         : FB_PickupDropout;
END_VAR

// 1. Calculate effective dropout thresholds
IF rHighDropout <> 0.0 THEN
    rEffHighDO := rHighDropout;
ELSIF rHysteresis > 0.0 THEN
    rEffHighDO := rHighPickup - rHysteresis;
ELSE
    rEffHighDO := rHighPickup;
END_IF;

IF rLowDropout <> 0.0 THEN
    rEffLowDO := rLowDropout;
ELSIF rHysteresis > 0.0 THEN
    rEffLowDO := rLowPickup + rHysteresis;
ELSE
    rEffLowDO := rLowPickup;
END_IF;


// 2. High threshold hysteresis evaluation
IF bEnableHigh THEN
    IF rVal >= rHighPickup THEN
        bHighCondition := TRUE;
    ELSIF rVal <= rEffHighDO THEN
        bHighCondition := FALSE;
    END_IF;
ELSE
    bHighCondition := FALSE;
END_IF;


// 3. Low threshold hysteresis evaluation
IF bEnableLow THEN
    IF rVal <= rLowPickup THEN
        bLowCondition := TRUE;
    ELSIF rVal >= rEffLowDO THEN
        bLowCondition := FALSE;
    END_IF;
ELSE
    bLowCondition := FALSE;
END_IF;


// 4. Pickup / Dropout timing filter
fbTimer(
    IN := (bHighCondition OR bLowCondition),
    tPickupDelay := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

bAlarm     := fbTimer.Q;
bPickup    := fbTimer.bPickup;
tElapsedPU := fbTimer.tElapsedPU;
tElapsedDO := fbTimer.tElapsedDO;


// 5. Diagnostic cause flags
IF bAlarm THEN
    bHighTrip := bHighCondition;
    bLowTrip  := bLowCondition;
ELSE
    bHighTrip := FALSE;
    bLowTrip  := FALSE;
END_IF;

END_FUNCTION_BLOCK

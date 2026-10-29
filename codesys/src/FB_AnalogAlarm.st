(* ==============================================================================
   FUNCTION BLOCK: FB_AnalogAlarm
   DESCRIPTION: IEC 61131-3 Structured Text implementation of an SEL RTAC-style
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
    {attribute 'symbol' := 'none'}
	rVal            : REAL;             (* Analog process value to monitor (e.g. Temperature) *)
    {attribute 'symbol' := 'none'}
    bEnableHigh     : BOOL := TRUE;     (* Enable High Alarm monitoring *)
    {attribute 'symbol' := 'none'}
    rHighPickup     : REAL := 0.0;      (* High trip pickup threshold *)
    {attribute 'symbol' := 'none'}
    rHighDropout    : REAL := 0.0;      (* High trip reset threshold (or leave 0.0 and use rHysteresis) *)
    {attribute 'symbol' := 'none'}
    bEnableLow      : BOOL := FALSE;    (* Enable Low Alarm monitoring *)
    {attribute 'symbol' := 'none'}
    rLowPickup      : REAL := 0.0;      (* Low trip pickup threshold *)
    {attribute 'symbol' := 'none'}
    rLowDropout     : REAL := 0.0;      (* Low trip reset threshold (or leave 0.0 and use rHysteresis) *)
    {attribute 'symbol' := 'none'}
    rHysteresis     : REAL := 0.0;      (* Optional deadband offset applied if Dropout not explicitly set *)
    {attribute 'symbol' := 'none'}
    tPickupDelay    : TIME := T#0S;     (* Time excursion must persist before alarm asserts *)
    {attribute 'symbol' := 'none'}
    tDropoutDelay   : TIME := T#0S;     (* Time normal state must persist before alarm clears *)
END_VAR
VAR_OUTPUT
    {attribute 'symbol' := 'read'}
	bAlarm          : BOOL := FALSE;    (* Filtered alarm output (Active Alarm) *)
    {attribute 'symbol' := 'read'}
    bPickup         : BOOL := FALSE;    (* Instantaneous pickup status (pre-timer) *)
    {attribute 'symbol' := 'none'}
    bHighTrip       : BOOL := FALSE;    (* TRUE if High Alarm condition caused/maintains trip *)
    {attribute 'symbol' := 'none'}
    bLowTrip        : BOOL := FALSE;    (* TRUE if Low Alarm condition caused/maintains trip *)
    {attribute 'symbol' := 'none'}
    tElapsedPU      : TIME := T#0S;     (* Current elapsed pickup timer *)
    {attribute 'symbol' := 'none'}
    tElapsedDO      : TIME := T#0S;     (* Current elapsed dropout timer *)
END_VAR
VAR
    {attribute 'symbol' := 'none'}
	rEffHighDO      : REAL;
    {attribute 'symbol' := 'none'}
    rEffLowDO       : REAL;
    {attribute 'symbol' := 'none'}
    bHighCondition  : BOOL := FALSE;
    {attribute 'symbol' := 'none'}
    bLowCondition   : BOOL := FALSE;
    {attribute 'symbol' := 'none'}
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


// 4. Pickup / Dropout timing filter (SEL RTAC PU_DO equivalent)
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

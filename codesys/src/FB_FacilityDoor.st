(* ==============================================================================
   FUNCTION BLOCK: FB_FacilityDoor
   DESCRIPTION: Encapsulated monitoring block for cleanroom and facility access doors
                (Main Entry, Procedure Room, Cryo Storage, Air Shower, Gown In/Out).
                Features:
                - Fail-safe normally closed contact supervision (24V/TRUE = Closed, 0V/FALSE = Open / Unwired)
                - Sustained open timer with contact chatter dropout filter (FB_PickupDropout)
                - Direct physical terminal binding (bDoorClosed)
                - Filtered alarm output to SCADA (bDoorAlarm)
   ============================================================================== *)
FUNCTION_BLOCK FB_FacilityDoor
VAR_INPUT
    bDoorClosed         : BOOL := FALSE;    (* Hardware DI: 24V/TRUE = Closed, 0V/FALSE = Open / Unwired *)
    tOpenAlarmDelay     : TIME := T#60M;    (* Sustained open threshold before alarm asserts *)
    tDropoutDelay       : TIME := T#5S;     (* Anti-chatter filter on door closure *)
END_VAR
VAR_OUTPUT
    bDoorAlarm          : BOOL := FALSE;    (* Filtered Priority 2 Alarm output to SCADA *)
END_VAR
VAR
    fbFilter            : FB_PickupDropout;
END_VAR

// TIMED DEBOUNCE FILTER FOR DOOR HELD OPEN ALARM
fbFilter(
    IN            := NOT bDoorClosed,
    tPickupDelay  := tOpenAlarmDelay,
    tDropoutDelay := tDropoutDelay
);
bDoorAlarm := fbFilter.Q;

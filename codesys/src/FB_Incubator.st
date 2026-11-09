(* ==============================================================================
   FUNCTION BLOCK: FB_Incubator
   DESCRIPTION: Encapsulated clinical monitoring block for Embryology Incubators
                (benchtop trigas, box incubators) via discrete dry alarm contacts.
                Features:
                - Pickup/Dropout debounce filter (FB_PickupDropout)
                - Direct physical terminal binding (bAlarmContact)
                - Cabinet door / post-close mute supervision (bMute)
   ============================================================================== *)
FUNCTION_BLOCK FB_Incubator
VAR_INPUT
    {attribute 'symbol' := 'none'}
    bAlarmContact       : BOOL := FALSE;    (* Physical dry alarm contact from incubator (FALSE = Normal, TRUE = Alarm) *)
    {attribute 'symbol' := 'read'}
    bMute               : BOOL := FALSE;    (* TRUE = Suppress alarm (Cabinet door open or recovery grace) *)
    {attribute 'symbol' := 'none'}
    tPickupDelay        : TIME := T#15S;    (* Contact bounce suppression filter *)
    {attribute 'symbol' := 'none'}
    tDropoutDelay       : TIME := T#5S;     (* Recovery confirmation filter *)
END_VAR
VAR_OUTPUT
    {attribute 'symbol' := 'read'}
    bAlarm              : BOOL := FALSE;    (* Filtered Priority 2 Alarm output to SCADA *)
    {attribute 'symbol' := 'read'}
    bMuted              : BOOL := FALSE;    (* Contact is tripped but suppressed by active mute *)
END_VAR
VAR
    {attribute 'symbol' := 'none'}
    fbFilter            : FB_PickupDropout;
END_VAR

// 1. TIMED DEBOUNCE FILTER
fbFilter(
    IN            := bAlarmContact,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

// 2. MUTE SUPERVISION
// When bMute is active (cabinet door open or post-close grace), suppress bAlarm.
bMuted := bMute AND fbFilter.Q;

IF bMute THEN
    bAlarm := FALSE;
ELSE
    bAlarm := fbFilter.Q;
END_IF;

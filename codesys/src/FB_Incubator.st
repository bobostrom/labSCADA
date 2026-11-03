(* ==============================================================================
   FUNCTION BLOCK: FB_Incubator
   DESCRIPTION: Encapsulated clinical monitoring block for Embryology Incubators
                (benchtop trigas, box incubators) via discrete dry alarm contacts.
                Features:
                - Granular per-device Virtual Simulation Mode (bSimMode)
                - Granular fault injection (bForceAlarm)
                - Pickup/Dropout debounce filter (FB_PickupDropout)
                - Direct physical terminal binding (bRawContact)
   ============================================================================== *)
FUNCTION_BLOCK FB_Incubator
VAR_INPUT
    {attribute 'symbol' := 'none'}
    bRawContact         : BOOL := FALSE;    (* Physical input terminal (FALSE = Normal, TRUE = Alarm) *)
    {attribute 'symbol' := 'none'}
    bSimMode            : BOOL := FALSE;    (* TRUE = Ignore terminal, use virtual override *)
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
    bAlarmContact       : BOOL := FALSE;    (* Unfiltered raw alarm contact status *)
    {attribute 'symbol' := 'read'}
    bMuted              : BOOL := FALSE;    (* Contact is tripped but suppressed by active mute *)
    {attribute 'symbol' := 'none'}
    tElapsedPU          : TIME := T#0S;
    {attribute 'symbol' := 'none'}
    tElapsedDO          : TIME := T#0S;
END_VAR
VAR
    {attribute 'symbol' := 'readwrite'}
    bForceAlarm         : BOOL := FALSE;    (* Forces alarm state during simulation *)
    {attribute 'symbol' := 'none'}
    fbFilter            : FB_PickupDropout;
END_VAR

// 1. INPUT SELECTION
IF bSimMode THEN
    bAlarmContact := bForceAlarm;
ELSE
    bAlarmContact := bRawContact;
END_IF;

// 2. TIMED DEBOUNCE FILTER
fbFilter(
    IN            := bAlarmContact,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

// 3. MUTE SUPERVISION
// When bMute is active (cabinet door open or post-close grace), suppress bAlarm.
bMuted := bMute AND fbFilter.Q;

IF bMute THEN
    bAlarm := FALSE;
ELSE
    bAlarm := fbFilter.Q;
END_IF;

tElapsedPU := fbFilter.tElapsedPU;
tElapsedDO := fbFilter.tElapsedDO;

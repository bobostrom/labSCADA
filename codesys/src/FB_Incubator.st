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
    {attribute 'symbol' := 'none'}
    tPickupDelay        : TIME := T#15S;    (* Contact bounce suppression filter *)
    {attribute 'symbol' := 'none'}
    tDropoutDelay       : TIME := T#5S;     (* Recovery confirmation filter *)
END_VAR
VAR_OUTPUT
    {attribute 'symbol' := 'read'}
    bAlarm              : BOOL := FALSE;    (* Filtered Priority 2 Alarm output to SCADA *)
    {attribute 'symbol' := 'none'}
    bInstantContact     : BOOL := FALSE;    (* Unfiltered raw contact status *)
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
    bInstantContact := bForceAlarm;
ELSE
    bInstantContact := bRawContact;
END_IF;

// 2. TIMED DEBOUNCE FILTER
fbFilter(
    IN            := bInstantContact,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

bAlarm     := fbFilter.Q;
tElapsedPU := fbFilter.tElapsedPU;
tElapsedDO := fbFilter.tElapsedDO;

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
    bRawContact         : BOOL := FALSE;    (* Physical input terminal (FALSE = Normal, TRUE = Alarm) *)
    bSimMode            : BOOL := FALSE;    (* TRUE = Ignore terminal, use virtual override *)
    bForceAlarm         : BOOL := FALSE;    (* Forces alarm state during simulation *)
    tPickupDelay        : TIME := T#15S;    (* Contact bounce suppression filter *)
    tDropoutDelay       : TIME := T#5S;     (* Recovery confirmation filter *)
END_VAR
VAR_OUTPUT
    bAlarm              : BOOL := FALSE;    (* Filtered Priority 2 Alarm output to SCADA *)
    bInstantContact     : BOOL := FALSE;    (* Unfiltered raw contact status *)
    tElapsedPU          : TIME := T#0S;
    tElapsedDO          : TIME := T#0S;
END_VAR
VAR
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

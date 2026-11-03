(* ==============================================================================
   FUNCTION BLOCK: FB_G210_Incubator
   DESCRIPTION: Encapsulated clinical monitoring block for K-Systems G210
                Multi-Chamber Incubators (10 Heated Zones).
                - 10 Chamber Zone Temperatures (Default 37.0°C)
                - Direct Physical Dry Alarm Contact (bAlarmContact)
                - Door/Recovery Mute Supervision (bMute)
                - Pickup/Dropout Debounce Filter
   ============================================================================== *)
FUNCTION_BLOCK FB_G210_Incubator
VAR_INPUT
    {attribute 'symbol' := 'readwrite'}
    bAlarmContact       : BOOL := FALSE;    (* Physical dry alarm contact from incubator (FALSE = Normal, TRUE = Alarm) *)
    {attribute 'symbol' := 'read'}
    bMute               : BOOL := FALSE;    (* TRUE = Suppress alarm (Cabinet door open or recovery grace) *)
    {attribute 'symbol' := 'none'}
    tPickupDelay        : TIME := T#15S;    (* Contact bounce filter *)
    {attribute 'symbol' := 'none'}
    tDropoutDelay       : TIME := T#5S;     (* Recovery confirmation filter *)
END_VAR
VAR_OUTPUT
    {attribute 'symbol' := 'read'}
    bAlarm              : BOOL := FALSE;    (* Filtered Priority 2 Alarm output to SCADA *)
    {attribute 'symbol' := 'read'}
    bMuted              : BOOL := FALSE;    (* Contact is tripped but actively suppressed by cabinet mute *)
    {attribute 'symbol' := 'read'}
    rZoneTemps          : ARRAY[1..10] OF REAL := [10(37.0)];  (* 10 Heated Chambers, Default 37.0 °C *)
END_VAR
VAR
    {attribute 'symbol' := 'none'}
    fbFilter            : FB_PickupDropout;
END_VAR

// 1. TIMED DEBOUNCE FILTER DIRECTLY ON ALARM CONTACT
fbFilter(
    IN            := bAlarmContact,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

// 2. MUTE SUPERVISION
// When bMute is TRUE (cabinet door open or grace period), suppress bAlarm.
bMuted := bMute AND fbFilter.Q;

IF bMute THEN
    bAlarm := FALSE;
ELSE
    bAlarm := fbFilter.Q;
END_IF;

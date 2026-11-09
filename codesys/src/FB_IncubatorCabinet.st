(* ==============================================================================
   FUNCTION BLOCK: FB_IncubatorCabinet
   DESCRIPTION: Enclosure microclimate and access supervision for benchtop
                incubator cabinet.
                Features:
                - Standardized fail-safe door contact supervision (Closed loop = Closed, Open loop = Open)
                - Autonomous incubator alarm muting while door is open
                - Post-closure recovery grace timer (TOF) to prevent nuisance alarms
                - Cabinet door left open alarm (TON)
                - Thermostatic exhaust fan control loop (hysteresis)
   ============================================================================== *)
FUNCTION_BLOCK FB_IncubatorCabinet
VAR_INPUT
    {attribute 'symbol' := 'readwrite'}
    bDoorClosed         : BOOL := FALSE;    (* Hardware DI: 24V/TRUE = Closed, 0V/FALSE = Open / Disconnected *)
    {attribute 'symbol' := 'none'}
    tDoorAlarmDelay     : TIME := T#3M;     (* Alarm if cabinet door left open longer than this *)
    {attribute 'symbol' := 'none'}
    tPostCloseGrace     : TIME := T#3M;     (* Time to keep incubator alarms muted after door closes *)
    {attribute 'symbol' := 'read'}
    rCabinetTemp        : REAL := 24.5;     (* Interior ambient temp (°C) *)
    {attribute 'symbol' := 'none'}
    rFanOnSetpoint      : REAL := 28.0;     (* Exhaust fan ON setpoint in °C *)
    {attribute 'symbol' := 'none'}
    rFanHysteresis      : REAL := 1.5;      (* Deadband in °C (turns off at 26.5°C) *)
END_VAR
VAR_OUTPUT
    {attribute 'symbol' := 'read'}
    bDoorAlarm          : BOOL := FALSE;    (* Alarm: Cabinet door held open past delay *)
    {attribute 'symbol' := 'read'}
    bIncubatorMute      : BOOL := FALSE;    (* TRUE while door is open OR during post-closure grace *)
    {attribute 'symbol' := 'read'}
    tGraceRemaining     : TIME := T#0S;     (* Time remaining in post-close recovery grace *)
    {attribute 'symbol' := 'read'}
    bFanCommand         : BOOL := FALSE;    (* Command to future DO fan relay *)
    {attribute 'symbol' := 'read'}
    bCabinetOvertemp    : BOOL := FALSE;    (* Alarm: Cabinet internal temp > 32°C *)
END_VAR
VAR
    {attribute 'symbol' := 'none'}
    tonDoorOpen         : TON;              (* Timer for door held open alert *)
    {attribute 'symbol' := 'none'}
    tofGrace            : TOF;              (* Off-delay timer keeping mute active post-closure *)
END_VAR

// ==============================================================================
// 1. CABINET DOOR HELD OPEN ALARM
//    Fail-safe hardware: 24V (TRUE) when closed, 0V (FALSE) when open/cut.
// ==============================================================================
tonDoorOpen(
    IN := NOT bDoorClosed,
    PT := tDoorAlarmDelay
);
bDoorAlarm := tonDoorOpen.Q;

// ==============================================================================
// 2. INCUBATOR ALARM MUTING & POST-CLOSE RECOVERY GRACE (TOF)
// ==============================================================================
// While bDoorClosed is FALSE (door open), tofGrace.Q is TRUE.
// When bDoorClosed transitions to TRUE, tofGrace.Q STAYS TRUE for tPostCloseGrace.
tofGrace(
    IN := NOT bDoorClosed,
    PT := tPostCloseGrace
);
bIncubatorMute := tofGrace.Q;

// Compute remaining grace time while door is closed but timer is still running
IF bDoorClosed AND tofGrace.Q THEN
    tGraceRemaining := tPostCloseGrace - tofGrace.ET;
ELSE
    tGraceRemaining := T#0S;
END_IF;

// ==============================================================================
// 4. THERMOSTATIC EXHAUST FAN CONTROL (HYSTERESIS)
// ==============================================================================
IF rCabinetTemp >= rFanOnSetpoint THEN
    bFanCommand := TRUE;
ELSIF rCabinetTemp <= (rFanOnSetpoint - rFanHysteresis) THEN
    bFanCommand := FALSE;
END_IF;

// ==============================================================================
// 5. CABINET OVERTEMPERATURE SUPERVISION
// ==============================================================================
bCabinetOvertemp := (rCabinetTemp >= 32.0);


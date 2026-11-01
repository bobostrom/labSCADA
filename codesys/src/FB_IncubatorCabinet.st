(* ==============================================================================
   FUNCTION BLOCK: FB_IncubatorCabinet
   DESCRIPTION: Enclosure microclimate and access supervision for benchtop
                incubator cabinet.
                Features:
                - Door switch monitoring with selectable polarity (NC / NO)
                - Autonomous incubator alarm muting while door is open
                - Post-closure recovery grace timer (TOF) to prevent nuisance alarms
                - Cabinet door left open alarm (TON)
                - Thermostatic exhaust fan control loop (hysteresis)
   ============================================================================== *)
FUNCTION_BLOCK FB_IncubatorCabinet
VAR_INPUT
    {attribute 'symbol' := 'none'}
    bRawDoorContact     : BOOL := FALSE;    (* Physical DI from 750-436 (Terminal 8 / DI 8) *)
    {attribute 'symbol' := 'none'}
    bDoorNormallyClosed : BOOL := TRUE;     (* TRUE = Closed loop (0V at DI when door closed) *)
    {attribute 'symbol' := 'none'}
    bSimMode            : BOOL := FALSE;    (* Virtual simulation mode *)
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
    bDoorOpen           : BOOL := FALSE;    (* Normalized door status: TRUE = Open, FALSE = Closed *)
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
    {attribute 'symbol' := 'readwrite'}
    bSimDoorOpen        : BOOL := FALSE;
    {attribute 'symbol' := 'none'}
    tonDoorOpen         : TON;              (* Timer for door held open alert *)
    {attribute 'symbol' := 'none'}
    tofGrace            : TOF;              (* Off-delay timer keeping mute active post-closure *)
END_VAR

// ==============================================================================
// 1. NORMALIZE DOOR CONTACT
// ==============================================================================
IF bSimMode THEN
    bDoorOpen := bSimDoorOpen;
ELSE
    IF bDoorNormallyClosed THEN
        // On 750-436 sink input:
        // Closed loop pulls DI to 0V (TRUE). When door opens, contact opens (FALSE).
        // Therefore, bDoorOpen is TRUE when bRawDoorContact is FALSE.
        bDoorOpen := NOT bRawDoorContact;
    ELSE
        // Open loop (closes when door opens)
        bDoorOpen := bRawDoorContact;
    END_IF;
END_IF;

// ==============================================================================
// 2. CABINET DOOR HELD OPEN ALARM
// ==============================================================================
tonDoorOpen(
    IN := bDoorOpen,
    PT := tDoorAlarmDelay
);
bDoorAlarm := tonDoorOpen.Q;

// ==============================================================================
// 3. INCUBATOR ALARM MUTING & POST-CLOSE RECOVERY GRACE (TOF)
// ==============================================================================
// While bDoorOpen is TRUE, tofGrace.Q is TRUE.
// When bDoorOpen transitions to FALSE, tofGrace.Q STAYS TRUE for tPostCloseGrace.
tofGrace(
    IN := bDoorOpen,
    PT := tPostCloseGrace
);
bIncubatorMute := tofGrace.Q;

// Compute remaining grace time while door is closed but timer is still running
IF (NOT bDoorOpen) AND tofGrace.Q THEN
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


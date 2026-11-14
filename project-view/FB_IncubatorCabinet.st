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
    bDoorClosed         : BOOL := FALSE;    (* Hardware DI: 24V/TRUE = Closed, 0V/FALSE = Open / Disconnected *)
    tDoorAlarmDelay     : TIME := T#3M;     (* Alarm if cabinet door left open longer than this *)
    tPostCloseGrace     : TIME := T#3M;     (* Time to keep incubator alarms muted after door closes *)
    wRawTempX10         : WORD := 16#D8F0;  (* Raw Modbus 750-461 register x10 (244 = 24.4°C, -9999 = 16#D8F0) *)
    rFanOnSetpoint      : REAL := 28.0;     (* Exhaust fan ON setpoint in °C *)
    rFanHysteresis      : REAL := 1.5;      (* Deadband in °C (turns off at 26.5°C) *)
END_VAR
VAR_OUTPUT
    bDoorAlarm          : BOOL := FALSE;    (* Alarm: Cabinet door held open past delay *)
    bIncubatorMute      : BOOL := FALSE;    (* TRUE while door is open OR during post-closure grace *)
    tGraceRemaining     : TIME := T#0S;     (* Time remaining in post-close recovery grace *)
    bFanCommand         : BOOL := FALSE;    (* Command to future DO fan relay *)
    bCabinetOvertemp    : BOOL := FALSE;    (* Alarm: Cabinet internal temp >= 32°C *)
    rProcessTemp        : REAL := -999.0;   (* Published cabinet temperature (°C) to SCADA & DB *)
    bProbeFault         : BOOL := TRUE;     (* Physical RTD probe open/short/out-of-range fault *)
END_VAR
VAR
    tonDoorOpen         : TON;              (* Timer for door held open alert *)
    tofGrace            : TOF;              (* Off-delay timer keeping mute active post-closure *)
    iTempX10            : INT;
END_VAR
// --- implementation ---
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
// 3. CABINET TEMPERATURE SCALING & PROBE FAULT SUPERVISION
// ==============================================================================
iTempX10    := TO_INT(wRawTempX10);
bProbeFault := (iTempX10 <= -2000) OR (iTempX10 >= 8500);

IF bProbeFault THEN
    rProcessTemp := -999.0;
ELSE
    rProcessTemp := TO_REAL(iTempX10) / 10.0;
END_IF;

// ==============================================================================
// 4. THERMOSTATIC EXHAUST FAN CONTROL (HYSTERESIS)
// ==============================================================================
IF bProbeFault THEN
    bFanCommand := FALSE;
ELSIF rProcessTemp >= rFanOnSetpoint THEN
    bFanCommand := TRUE;
ELSIF rProcessTemp <= (rFanOnSetpoint - rFanHysteresis) THEN
    bFanCommand := FALSE;
END_IF;

// ==============================================================================
// 5. CABINET OVERTEMPERATURE SUPERVISION
// ==============================================================================
bCabinetOvertemp := (NOT bProbeFault) AND (rProcessTemp >= 32.0);
END_FUNCTION

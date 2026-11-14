(* ==============================================================================
   FUNCTION BLOCK: FB_MedFridge
   DESCRIPTION: Encapsulated clinical monitoring block for Medical Refrigerators
                (embryo media, medications, specimens).
                - Scaled raw integer input (wRawTempX10 / 10.0 -> °C)
                - First-order thermal mass filter (FB_ThermalVial) emulating a buffer vial
                - Dual-limit Window Alarm (1.0°C to 8.5°C/10.0°C) on virtual-vial temp
                - Option A pre-alarm warning (bWarn) from temperature margin bands
                - Clinical fault supervision (Open circuit, wiring short, comms loss)
   ============================================================================== *)
FUNCTION_BLOCK FB_MedFridge
VAR_INPUT
    wRawTempX10         : WORD := 16#D8F0;  (* Raw Modbus register (Fridge scaled temp * 10, -9999 = 16#D8F0) *)
    rHighTrip           : REAL := 8.5;      (* CAP excursion threshold (override to 10.0 in AFOA PLC_PRG) *)
    rLowTrip            : REAL := 1.0;      (* Freezing prevention threshold (1.0°C clinical alarm per equipment.json) *)
    rHysteresis         : REAL := 0.5;      (* Anti-chatter deadband (°C) *)
    tPickupDelay        : TIME := T#0S;     (* Binary pickup delay (T#0S when using virtual-vial damping) *)
    tDropoutDelay       : TIME := T#0S;     (* Binary dropout delay (hysteresis handles anti-chatter) *)
    tThermalTau         : TIME := T#5M;     (* Virtual buffer vial time constant; T#0S bypasses filtering *)
    rHighWarnMargin     : REAL := 1.5;      (* Pre-alarm warn margin below rHighTrip (8.5°C when High=10.0°C) *)
    rLowWarnMargin      : REAL := 1.0;      (* Pre-alarm warn margin above rLowTrip (2.0°C when Low=1.0°C) *)
    uiRawFaultCode      : UINT := 0;        (* Probe fault code: 0=OK, 0xFF=Unpopulated *)
    bCommLoss           : BOOL := FALSE;    (* Watchdog comms loss flag *)
END_VAR
VAR_OUTPUT
    rProcessTemp        : REAL := -999.0;   (* Virtual-vial temperature to SCADA & DB (°C) *)
    rRawTemp            : REAL := -999.0;   (* Instantaneous unfiltered air temperature (°C) *)
    bAlarm              : BOOL := FALSE;    (* Priority 2 Emergency Alarm flag *)
    bWarn               : BOOL := FALSE;    (* Priority 1 Pre-alarm warning flag (margin band or pickup delay) *)
    bProbeFault         : BOOL := TRUE;     (* Physical probe disconnected or shorted *)
END_VAR
VAR
    iTempX10            : INT;
    bHealthy            : BOOL;
    fbThermalVial       : FB_ThermalVial;
    fbAlarmEval         : FB_AnalogAlarm;
    fbWarnEval          : FB_AnalogAlarm;
END_VAR
VAR CONSTANT
    cZero               : REAL := 0.0;
END_VAR
// --- implementation ---
// ==============================================================================
// 1. HARDWARE HEALTH & RAW AIR TEMPERATURE SCALING
// ==============================================================================
iTempX10    := TO_INT(wRawTempX10);
bProbeFault := (uiRawFaultCode <> 0) OR (iTempX10 <= -9000) OR (iTempX10 >= 9000);
bHealthy    := NOT (bProbeFault OR bCommLoss);

IF NOT bHealthy THEN
    rRawTemp := -999.0;
ELSE
    rRawTemp := TO_REAL(iTempX10) / 10.0;
END_IF;

// ==============================================================================
// 2. VIRTUAL BUFFER VIAL FILTER (5-Minute Thermal Time Constant)
// ==============================================================================
fbThermalVial(
    rRawTemp    := rRawTemp,
    bValid      := bHealthy,
    tThermalTau := tThermalTau
);
rProcessTemp := fbThermalVial.rVialTemp;

// ==============================================================================
// 3. CLINICAL ALARM & PRE-ALARM MARGIN EVALUATION (Dual-Limit Window)
// ==============================================================================
fbAlarmEval(
    rVal          := rProcessTemp,
    bEnableHigh   := bHealthy,
    rHighPickup   := rHighTrip,
    rHighDropout  := rHighTrip - rHysteresis,
    bEnableLow    := bHealthy,
    rLowPickup    := rLowTrip,
    rLowDropout   := rLowTrip + rHysteresis,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

fbWarnEval(
    rVal        := rProcessTemp,
    bEnableHigh := bHealthy AND (rHighWarnMargin > cZero),
    rHighPickup := rHighTrip - rHighWarnMargin,
    bEnableLow  := bHealthy AND (rLowWarnMargin > cZero),
    rLowPickup  := rLowTrip + rLowWarnMargin,
    rHysteresis := rHysteresis
);

bAlarm := fbAlarmEval.bAlarm;
bWarn  := fbAlarmEval.bWarn OR (fbWarnEval.bAlarm AND NOT fbAlarmEval.bAlarm);
END_FUNCTION

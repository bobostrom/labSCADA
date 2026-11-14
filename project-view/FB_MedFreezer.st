(* ==============================================================================
   FUNCTION BLOCK: FB_MedFreezer
   DESCRIPTION: Encapsulated clinical monitoring block for Medical Freezers
                (-20°C sperm/media or -80°C ultra-low freezers).
                - Scaled raw integer input (wRawTempX10 / 10.0 -> °C)
                - First-order thermal mass filter (FB_ThermalVial) emulating a buffer vial
                - High temperature threshold alarm on virtual-vial temperature
                - Option A pre-alarm warning (bWarn) from temperature margin band
                - Clinical fault supervision (Open circuit, wiring short, comms loss)
   ============================================================================== *)
FUNCTION_BLOCK FB_MedFreezer
VAR_INPUT
    wRawTempX10         : WORD := 16#D8F0;  (* Offset 0: Raw Modbus register (-9999 = 16#D8F0 Sentinel / Disconnected) *)
    rHighTrip           : REAL := -10.0;    (* Medications/consumables warm alarm threshold (°C) per USP <1079> *)
    rHysteresis         : REAL := 0.5;      (* Anti-chatter deadband (°C) - resets at -10.5°C *)
    tPickupDelay        : TIME := T#0S;     (* Binary pickup delay (T#0S when using virtual-vial damping) *)
    tDropoutDelay       : TIME := T#0S;     (* Binary dropout delay (hysteresis handles anti-chatter) *)
    tThermalTau         : TIME := T#8M;     (* Virtual buffer vial time constant; T#0S bypasses filtering *)
    rHighWarnMargin     : REAL := 2.0;      (* Pre-alarm warn margin below rHighTrip (-12.0°C when High=-10.0°C) *)
    uiRawFaultCode      : UINT := 0;        (* Probe fault code: 0=OK, 0xFF=Unpopulated *)
    bCommLoss           : BOOL := FALSE;    (* Watchdog comms loss flag *)
END_VAR
VAR_OUTPUT
    rProcessTemp        : REAL := -999.0;   (* Virtual-vial temperature to SCADA & DB (°C) *)
    rRawTemp            : REAL := -999.0;   (* Instantaneous unfiltered air temperature (°C) *)
    bAlarm              : BOOL := FALSE;    (* Priority 2 Emergency Alarm flag *)
    bWarn               : BOOL := FALSE;    (* Priority 1 Pre-alarm warning flag (margin band or pickup delay) *)
    bProbeFault         : BOOL := TRUE;     (* Probe disconnected or hardware fault *)
END_VAR
VAR
    iTempX10            : INT;
    bHealthy            : BOOL;
    fbThermalVial       : FB_ThermalVial;
    fbAlarmEval         : FB_AnalogAlarm;
    fbWarnEval          : FB_AnalogAlarm;
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
// 2. VIRTUAL BUFFER VIAL FILTER (8-Minute Thermal Time Constant)
// ==============================================================================
fbThermalVial(
    rRawTemp    := rRawTemp,
    bValid      := bHealthy,
    tThermalTau := tThermalTau
);
rProcessTemp := fbThermalVial.rVialTemp;

// ==============================================================================
// 3. CLINICAL ALARM & PRE-ALARM MARGIN EVALUATION
// ==============================================================================
fbAlarmEval(
    rVal          := rProcessTemp,
    bEnableHigh   := bHealthy,
    rHighPickup   := rHighTrip,
    rHighDropout  := rHighTrip - rHysteresis,
    bEnableLow    := FALSE,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

fbWarnEval(
    rVal        := rProcessTemp,
    bEnableHigh := bHealthy AND (rHighWarnMargin > 0.0),
    rHighPickup := rHighTrip - rHighWarnMargin,
    rHysteresis := rHysteresis,
    bEnableLow  := FALSE
);

bAlarm := fbAlarmEval.bAlarm;
bWarn  := fbAlarmEval.bWarn OR (fbWarnEval.bAlarm AND NOT fbAlarmEval.bAlarm);
END_FUNCTION

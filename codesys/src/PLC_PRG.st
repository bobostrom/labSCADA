(* ==============================================================================
   PROGRAM: PLC_PRG
   DESCRIPTION: Main execution program for CODESYS Controller.
                Configured with IVF Laboratory telemetry points, alarm evaluation,
                hysteresis, draft/on-delay timers, and simulation fault injections.
   ============================================================================== *)
PROGRAM PLC_PRG
VAR
    (* --- Heartbeat & LED Blinker --- *)
	fbLedU1 : FbAppLED_SetBlink;

    (* --- Analog Telemetry: Temperatures --- *)
    rLabAmbientTemp         : REAL := 25.0;     (* Target ~25.0 °C *)
    rMedFridgeTemp          : REAL := 3.0;      (* Target ~3.0 °C (Normal: 2.0°C to 8.0°C) *)
    rMedFreezerTemp         : REAL := -20.0;    (* Target ~ -20.0 °C (Normal: < -15.0°C) *)
    rCryoTank1Temp           : REAL := -150.0;   (* Target ~ -150.0 °C (Normal: < -135.0°C) *)
	rCryoTank2Temp           : REAL := -150.0;   (* Target ~ -150.0 °C (Normal: < -135.0°C) *)

    (* --- Discrete Telemetry: Door Contacts & Physical State --- *)
    bDoor01_MainDoor        : BOOL := FALSE;    (* FALSE = Closed, TRUE = Open *)
    bDoor02_CryoLabDoor     : BOOL := FALSE;    (* FALSE = Closed, TRUE = Open *)

    (* --- Discrete Clinical Alarm Outputs (Published over OPC UA) --- *)
    bMedFridgeAlarm         : BOOL := FALSE;    (* TRUE when Fridge > 8.0°C or < 2.0°C for > 2m *)
    bMedFreezerAlarm        : BOOL := FALSE;    (* TRUE when Freezer > -15.0°C for > 3m *)
    bCryoTank1Alarm          : BOOL := FALSE;    (* TRUE when Cryo Tank > -135.0°C for > 30s *)
    bCryoTank2Alarm          : BOOL := FALSE;    (* TRUE when Cryo Tank > -135.0°C for > 30s *)
    bDoor01_Alarm           : BOOL := FALSE;    (* TRUE when Main Door held open > 3m *)
    bDoor02_Alarm           : BOOL := FALSE;    (* TRUE when Cryo Door held open > 3m *)
    bIncubator01_Alarm      : BOOL := FALSE;    (* Incubator 01 Alarm Contact *)
    bIncubator02_Alarm      : BOOL := FALSE;    (* Incubator 02 Alarm Contact *)

    (* --- Clinical Alarm Function Blocks (RTAC-Style Pickup / Dropout & Hysteresis) --- *)
    fbFridgeAlarm           : FB_AnalogAlarm;
    fbFreezerAlarm          : FB_AnalogAlarm;
    fbCryo1Alarm             : FB_AnalogAlarm;
	fbCryo2Alarm             : FB_AnalogAlarm;
    fbDoor01Alarm           : FB_PickupDropout;
    fbDoor02Alarm           : FB_PickupDropout;


    (* --- Simulation & Fault Injection Controls --- *)
    tonSimTick              : TON;
    iSimStep                : INT := 0;
    bSimulateDynamics       : BOOL := TRUE;     (* Set to FALSE to hold static values *)

    (* Toggle these bits in CODESYS online monitoring to test alarms instantly *)
    bForceFridgeExcursion   : BOOL := FALSE;    (* Forces fridge to 9.5°C *)
    bForceFreezerExcursion  : BOOL := FALSE;    (* Forces freezer to -12.0°C *)
    bForceCryo1Excursion     : BOOL := FALSE;    (* Forces cryo tank to -125.0°C *)
	bForceCryo2Excursion     : BOOL := FALSE;    (* Forces cryo tank to -125.0°C *)
    bForceDoor01Ajar        : BOOL := FALSE;    (* Forces Main Door open *)
    bForceDoor02Ajar        : BOOL := FALSE;    (* Forces Cryo Door open *)
    bForceIncubator01Alarm  : BOOL := FALSE;    (* Forces Incubator 01 alarm contact *)
    bForceIncubator02Alarm  : BOOL := FALSE;    (* Forces Incubator 02 alarm contact *)
END_VAR


// ==============================================================================
// 1. SYSTEM HEARTBEAT BLINKER
// ==============================================================================
fbLedU1(xEnable := TRUE, eLedID := 1,tTime1 :=T#1S,tTime2 :=T#500MS,eLedColor1 := Green, eLedColor2 := Yellow);

// ==============================================================================
// 2. IVF LAB TELEMETRY SIMULATION & FAULT INJECTION
// ==============================================================================
tonSimTick(IN := NOT tonSimTick.Q, PT := T#1S);

IF tonSimTick.Q AND bSimulateDynamics THEN
    iSimStep := (iSimStep + 1) MOD 360;

    // Lab Ambient: smooth drift around 25.0 °C (24.7 °C to 25.3 °C)
    rLabAmbientTemp := 25.0 + 0.3 * SIN(TO_REAL(iSimStep) * 0.05);

    // Medical Fridge: refrigeration cycle around 3.0 °C (2.6 °C to 3.4 °C)
    IF bForceFridgeExcursion THEN
        rMedFridgeTemp := 9.5 + 0.4 * COS(TO_REAL(iSimStep) * 0.08);   // Over 8.0°C limit
    ELSE
        rMedFridgeTemp := 3.0 + 0.4 * COS(TO_REAL(iSimStep) * 0.08);
    END_IF;

    // Medical Freezer: compressor cycle around -20.0 °C (-20.6 °C to -19.4 °C)
    IF bForceFreezerExcursion THEN
        rMedFreezerTemp := -12.0  + 0.6 * SIN(TO_REAL(iSimStep) * 0.06); // Over -15.0°C limit
    ELSE
        rMedFreezerTemp := -20.0 + 0.6 * SIN(TO_REAL(iSimStep) * 0.06);
    END_IF;

    // Cryo Tank1: vapor phase LN2 thermal dynamics around -150.0 °C
    IF bForceCryo1Excursion THEN
        rCryoTank1Temp := -125.0 + 0.8 * COS(TO_REAL(iSimStep) * 0.03);  // Danger zone above -135.0°C
    ELSE
        rCryoTank1Temp := -150.0 + 0.8 * COS(TO_REAL(iSimStep) * 0.03);
    END_IF;

    // Cryo Tank2: vapor phase LN2 thermal dynamics around -150.0 °C
    IF bForceCryo2Excursion THEN
        rCryoTank2Temp := -125.0 + 0.8 * COS(TO_REAL(iSimStep) * 0.035);  // Danger zone above -135.0°C
    ELSE
        rCryoTank2Temp := -150.0 + 0.8 * COS(TO_REAL(iSimStep) * 0.035);
    END_IF;

    // Doors Simulation / Overrides
    IF bForceDoor01Ajar THEN
        bDoor01_MainDoor := TRUE;
    ELSE
        bDoor01_MainDoor := FALSE;
    END_IF;

    IF bForceDoor02Ajar THEN
        bDoor02_CryoLabDoor := TRUE;
    ELSE
        bDoor02_CryoLabDoor := FALSE;
    END_IF;

    // Incubators Simulated Contacts
    bIncubator01_Alarm := bForceIncubator01Alarm;
    bIncubator02_Alarm := bForceIncubator02Alarm;
END_IF;


// ==============================================================================
// 3. CLINICAL ALARM EVALUATION (PICKUP / DROPOUT & HYSTERESIS)
// ==============================================================================

// --- A. Medical Fridge Alarm (Normal: 2.0°C to 8.0°C, 2m pickup, 10s dropout) ---
fbFridgeAlarm(
    rVal          := rMedFridgeTemp,
    bEnableHigh   := TRUE,
    rHighPickup   := 8.5,
    rHighDropout  := 7.5,      // 0.5°C hysteresis
    bEnableLow    := TRUE,
    rLowPickup    := 2.0,
    rLowDropout   := 2.5,      // 0.5°C hysteresis
    tPickupDelay  := T#2M,     // Sustained excursion required to trip
    tDropoutDelay := T#10S     // Clean recovery required to reset
);
bMedFridgeAlarm := fbFridgeAlarm.bAlarm;


// --- B. Medical Freezer Alarm (Normal: < -15.0°C, 3m pickup, 10s dropout) ---
fbFreezerAlarm(
    rVal          := rMedFreezerTemp,
    bEnableHigh   := TRUE,
    rHighPickup   := -15.0,
    rHighDropout  := -16.5,    // 1.5°C hysteresis
    bEnableLow    := FALSE,
    tPickupDelay  := T#3M,     // Sustained warm excursion required to trip
    tDropoutDelay := T#10S     // Clean recovery required to reset
);
bMedFreezerAlarm := fbFreezerAlarm.bAlarm;


// --- C. Cryogenic LN2 Tank Alarm (Normal: < -135.0°C, 30s pickup, 10s dropout) ---
fbCryo1Alarm(
    rVal          := rCryoTank1Temp,
    bEnableHigh   := TRUE,
    rHighPickup   := -135.0,
    rHighDropout  := -140.0,   // 5.0°C hysteresis
    bEnableLow    := FALSE,
    tPickupDelay  := T#30S,    // Rapid critical LN2 warning
    tDropoutDelay := T#10S     // Clean LN2 fill required to reset
);
bCryoTank1Alarm := fbCryo1Alarm.bAlarm;

fbCryo2Alarm(
    rVal          := rCryoTank2Temp,
    bEnableHigh   := TRUE,
    rHighPickup   := -135.0,
    rHighDropout  := -140.0,   // 5.0°C hysteresis
    bEnableLow    := FALSE,
    tPickupDelay  := T#30S,    // Rapid critical LN2 warning
    tDropoutDelay := T#10S     // Clean LN2 fill required to reset
);
bCryoTank2Alarm := fbCryo2Alarm.bAlarm;



// --- D. Cleanroom Doors Ajar Alarms (> 3 minutes open) ---
fbDoor01Alarm(
    IN            := bDoor01_MainDoor,
    tPickupDelay  := T#3M,
    tDropoutDelay := T#5S
);
bDoor01_Alarm := fbDoor01Alarm.Q;

fbDoor02Alarm(
    IN            := bDoor02_CryoLabDoor,
    tPickupDelay  := T#3M,
    tDropoutDelay := T#5S
);
bDoor02_Alarm := fbDoor02Alarm.Q;


END_PROGRAM;


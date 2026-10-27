(* ==============================================================================
   PROGRAM: PLC_PRG
   DESCRIPTION: Main execution program for CODESYS Controller (Demo & Production).
                Configured with IVF Laboratory telemetry points, modular clinical
                equipment function blocks, debounced pickup/dropout timing filters,
                and on-demand simulation fault injection.
   ============================================================================== *)
PROGRAM PLC_PRG
VAR
    (* --- System Heartbeat Blinker (Pure IEC 61131-3) --- *)
    tonBlink                : TON;
    bHeartbeat              : BOOL := FALSE;

    (* --- Analog Telemetry: Published over OPC UA --- *)
    rLabAmbientTemp         : REAL := 25.0;     (* Target ~25.0 °C *)
    rMedFridgeTemp          : REAL := 3.5;      (* Target ~3.0 °C (Normal: 2.0°C to 8.0°C) *)
    rMedFreezerTemp         : REAL := -20.0;    (* Target ~ -20.0 °C (Normal: < -15.0°C) *)
    rDewar1Temp             : REAL := -150.0;   (* Target ~ -150.0 °C (Normal: < -135.0°C) *)
    rDewar2Temp             : REAL := -150.0;   (* Target ~ -150.0 °C (Normal: < -135.0°C) *)

    (* --- Discrete Telemetry: Door Contacts Published over OPC UA --- *)
    bDoor01_MainDoor        : BOOL := FALSE;    (* FALSE = Closed, TRUE = Open *)
    bDoor02_CryoLabDoor     : BOOL := FALSE;    (* FALSE = Closed, TRUE = Open *)

    (* --- Discrete Clinical Alarm Outputs Published over OPC UA --- *)
    bMedFridgeAlarm         : BOOL := FALSE;    (* TRUE when Fridge > 8.5°C or < 2.0°C for > 2m *)
    bMedFreezerAlarm        : BOOL := FALSE;    (* TRUE when Freezer > -15.0°C for > 3m *)
    bDewar1Alarm            : BOOL := FALSE;    (* TRUE when Dewar 1 > -135.0°C for > 30s *)
    bDewar2Alarm            : BOOL := FALSE;    (* TRUE when Dewar 2 > -135.0°C for > 30s *)
    bDoor01_Alarm           : BOOL := FALSE;    (* TRUE when Main Door held open > 3m *)
    bDoor02_Alarm           : BOOL := FALSE;    (* TRUE when Cryo Door held open > 3m *)
    bIncubator01_Alarm      : BOOL := FALSE;    (* Incubator 01 Alarm Contact *)
    bIncubator02_Alarm      : BOOL := FALSE;    (* Incubator 02 Alarm Contact *)

    (* --- Discrete Pre-Alarm Pickup / Delay States Published over OPC UA --- *)
    bMedFridgeWarn          : BOOL := FALSE;    (* TRUE during excursion pickup delay *)
    bMedFreezerWarn         : BOOL := FALSE;    (* TRUE during freezer warm pickup delay *)
    bDewar1Warn             : BOOL := FALSE;    (* TRUE during Dewar 1 warm pickup delay *)
    bDewar2Warn             : BOOL := FALSE;    (* TRUE during Dewar 2 warm pickup delay *)

    (* --- Encapsulated Clinical Equipment Function Blocks --- *)
    fbFridge                : FB_MedFridge;
    fbFreezer               : FB_MedFreezer;
    fbDewar1                : FB_Dewar;
    fbDewar2                : FB_Dewar;
    fbIncubator1            : FB_Incubator;
    fbIncubator2            : FB_Incubator;
    fbDoor01                : FB_PickupDropout;
    fbDoor02                : FB_PickupDropout;

    (* --- Ambient Room Drift Dynamics --- *)
    tonAmbientTick          : TON;
    iAmbientStep            : INT := 0;

    (* --- Master Simulation & Fault Injection Controls --- *)
    bGlobalSimMode          : BOOL := TRUE;     (* TRUE = Demo Virtual Simulation; FALSE = Live Hardware Probes *)

    (* Toggle these bits in CODESYS online monitoring to test alarms on demand *)
    bForceFridgeExcursion   : BOOL := FALSE;    (* Injects 9.5°C warm excursion into Refrigerator *)
    bForceFreezerExcursion  : BOOL := FALSE;    (* Injects -12.0°C warm excursion into Freezer *)
    bForceDewar1Excursion   : BOOL := FALSE;    (* Injects -125.0°C critical boil-off into Dewar 1 *)
    bForceDewar2Excursion   : BOOL := FALSE;    (* Injects -125.0°C critical boil-off into Dewar 2 *)
    bForceIncubator01Alarm  : BOOL := FALSE;    (* Forces Incubator 01 dry alarm contact *)
    bForceIncubator02Alarm  : BOOL := FALSE;    (* Forces Incubator 02 dry alarm contact *)
END_VAR

// ==============================================================================
// 1. SYSTEM HEARTBEAT BLINKER (1 Hz)
// ==============================================================================
tonBlink(IN := NOT tonBlink.Q, PT := T#500MS);
IF tonBlink.Q THEN
    bHeartbeat := NOT bHeartbeat;
END_IF;

// ==============================================================================
// 2. LAB AMBIENT TEMPERATURE SIMULATION
// ==============================================================================
tonAmbientTick(IN := NOT tonAmbientTick.Q, PT := T#1S);
IF tonAmbientTick.Q THEN
    iAmbientStep := (iAmbientStep + 1) MOD 360;
    rLabAmbientTemp := 25.0 + 0.3 * SIN(TO_REAL(iAmbientStep) * 0.05);
END_IF;

// ==============================================================================
// 3. ENCAPSULATED CLINICAL EQUIPMENT BLOCKS
// ==============================================================================

// --- A. Medical Refrigerator (2.0°C to 8.0°C, 2m pickup, 10s dropout) ---
fbFridge(
    rRawTemp        := 3.5,
    rNominalTemp    := 3.5,
    bSimMode        := bGlobalSimMode,
    bForceExcursion := bForceFridgeExcursion
);
rMedFridgeTemp  := fbFridge.rProcessTemp;
bMedFridgeAlarm := fbFridge.bAlarm;
bMedFridgeWarn  := fbFridge.bWarn;

// --- B. Medical Freezer (< -15.0°C, 3m pickup, 10s dropout) ---
fbFreezer(
    rRawTemp        := -20.0,
    rNominalTemp    := -20.0,
    bSimMode        := bGlobalSimMode,
    bForceExcursion := bForceFreezerExcursion
);
rMedFreezerTemp  := fbFreezer.rProcessTemp;
bMedFreezerAlarm := fbFreezer.bAlarm;
bMedFreezerWarn  := fbFreezer.bWarn;

// --- C. Cryogenic LN2 Dewar 1 (< -135.0°C, 30s pickup, 10s dropout) ---
fbDewar1(
    rRawTemp        := -151.2,
    rNominalTemp    := -151.2,
    rPhaseOffset    := 0.0,
    bSimMode        := bGlobalSimMode,
    bForceExcursion := bForceDewar1Excursion
);
rDewar1Temp  := fbDewar1.rProcessTemp;
bDewar1Alarm := fbDewar1.bAlarm;
bDewar1Warn  := fbDewar1.bWarn;

// --- D. Cryogenic LN2 Dewar 2 (< -135.0°C, 30s pickup, 10s dropout) ---
fbDewar2(
    rRawTemp        := -149.4,
    rNominalTemp    := -149.4,
    rPhaseOffset    := 2.3,
    bSimMode        := bGlobalSimMode,
    bForceExcursion := bForceDewar2Excursion
);
rDewar2Temp  := fbDewar2.rProcessTemp;
bDewar2Alarm := fbDewar2.bAlarm;
bDewar2Warn  := fbDewar2.bWarn;

// --- E. Embryology Incubator 01 (Dry contact with 15s debounce) ---
fbIncubator1(
    bSimMode    := bGlobalSimMode,
    bForceAlarm := bForceIncubator01Alarm
);
bIncubator01_Alarm := fbIncubator1.bAlarm;

// --- F. Embryology Incubator 02 (Dry contact with 15s debounce) ---
fbIncubator2(
    bSimMode    := bGlobalSimMode,
    bForceAlarm := bForceIncubator02Alarm
);
bIncubator02_Alarm := fbIncubator2.bAlarm;

// --- G. Cleanroom Main & Cryo Lab Doors (3-minute open timer) ---
fbDoor01(
    IN            := bDoor01_MainDoor,
    tPickupDelay  := T#3M,
    tDropoutDelay := T#5S
);
bDoor01_Alarm := fbDoor01.Q;

fbDoor02(
    IN            := bDoor02_CryoLabDoor,
    tPickupDelay  := T#3M,
    tDropoutDelay := T#5S
);
bDoor02_Alarm := fbDoor02.Q;

END_PROGRAM

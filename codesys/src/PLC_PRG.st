(* ==============================================================================
   PROGRAM: PLC_PRG
   DESCRIPTION: Main execution program for CODESYS Controller (Demo & Production).
                Configured with IVF Laboratory telemetry points, modular clinical
                equipment function blocks, debounced pickup/dropout timing filters,
                and on-demand simulation fault injection.
                OPC UA clients subscribe directly to the Function Block outputs
                (e.g. fbDewar1.rProcessTemp, fbDewar1.bAlarm, fbDewar1.bWarn).
   ============================================================================== *)
PROGRAM PLC_PRG
VAR
    (* --- System Heartbeat Blinker (Pure IEC 61131-3) --- *)
    {attribute 'symbol' := 'none'}
    tonBlink                : TON;
    bHeartbeat              : BOOL := FALSE;

    (* --- Analog Telemetry: Room Ambient Published over OPC UA --- *)
    {attribute 'symbol' := 'read'}
    rLabAmbientTemp         : REAL := 25.0;     (* Target ~25.0 °C *)

    (* --- Discrete Telemetry: Physical Door Contacts Published over OPC UA --- *)
    {attribute 'symbol' := 'read'}
    bDoor01_MainDoor        : BOOL := FALSE;    (* FALSE = Closed, TRUE = Open *)
    {attribute 'symbol' := 'read'}
    bDoor02_CryoLabDoor     : BOOL := FALSE;    (* FALSE = Closed, TRUE = Open *)

    (* --- Encapsulated Clinical Equipment Function Blocks (Published over OPC UA) --- *)
    fbFridge                : FB_MedFridge;
    fbFreezer               : FB_MedFreezer;
    fbDewar1                : FB_Dewar;
    fbDewar2                : FB_Dewar;
    fbDewar3                : FB_Dewar;
    fbDewar4                : FB_Dewar;
    fbDewar5                : FB_Dewar;
    fbIncubator1            : FB_Incubator;
    fbIncubator2            : FB_Incubator;
    fbDoor01                : FB_PickupDropout;
    fbDoor02                : FB_PickupDropout;

    (* --- Ambient Room Drift Dynamics --- *)
    {attribute 'symbol' := 'none'}
    tonAmbientTick          : TON;
    {attribute 'symbol' := 'none'}
    iAmbientStep            : INT := 0;

    (* --- Master Simulation & Fault Injection Controls --- *)
    bGlobalSimMode          : BOOL := TRUE;     (* TRUE = Demo Virtual Simulation; FALSE = Live Hardware Probes *)

    (* Toggle these bits in CODESYS online monitoring (or directly on each FB) to test alarms on demand *)
    bForceFridgeExcursion   : BOOL := FALSE;    (* Injects 9.5°C warm excursion into Refrigerator *)
    bForceFreezerExcursion  : BOOL := FALSE;    (* Injects -12.0°C warm excursion into Freezer *)
    bForceDewar1Excursion   : BOOL := FALSE;    (* Injects -125.0°C critical boil-off into Dewar 1 *)
    bForceDewar2Excursion   : BOOL := FALSE;    (* Injects -125.0°C critical boil-off into Dewar 2 *)
    bForceDewar3Excursion   : BOOL := FALSE;    (* Injects -125.0°C critical boil-off into Dewar 3 *)
    bForceDewar4Excursion   : BOOL := FALSE;    (* Injects -125.0°C critical boil-off into Dewar 4 *)
    bForceDewar5Excursion   : BOOL := FALSE;    (* Injects -125.0°C critical boil-off into Dewar 5 *)
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

// --- B. Medical Freezer (< -15.0°C, 3m pickup, 10s dropout) ---
fbFreezer(
    rRawTemp        := -20.0,
    rNominalTemp    := -20.0,
    bSimMode        := bGlobalSimMode,
    bForceExcursion := bForceFreezerExcursion
);

// --- C. Cryogenic LN2 Dewars 1 - 5 (< -135.0°C, 30s pickup, 10s dropout) ---
fbDewar1(
    rRawTemp        := -150.0,
    rNominalTemp    := -150.0,
    bSimMode        := bGlobalSimMode,
    bForceExcursion := bForceDewar1Excursion
);

fbDewar2(
    rRawTemp        := -150.0,
    rNominalTemp    := -150.0,
    bSimMode        := bGlobalSimMode,
    bForceExcursion := bForceDewar2Excursion
);

fbDewar3(
    rRawTemp        := -150.0,
    rNominalTemp    := -150.0,
    bSimMode        := bGlobalSimMode,
    bForceExcursion := bForceDewar3Excursion
);

fbDewar4(
    rRawTemp        := -150.0,
    rNominalTemp    := -150.0,
    bSimMode        := bGlobalSimMode,
    bForceExcursion := bForceDewar4Excursion
);

fbDewar5(
    rRawTemp        := -150.0,
    rNominalTemp    := -150.0,
    bSimMode        := bGlobalSimMode,
    bForceExcursion := bForceDewar5Excursion
);

// --- D. Embryology Incubators 01 & 02 (Dry contact with 15s debounce) ---
fbIncubator1(
    bSimMode    := bGlobalSimMode,
    bForceAlarm := bForceIncubator01Alarm
);

fbIncubator2(
    bSimMode    := bGlobalSimMode,
    bForceAlarm := bForceIncubator02Alarm
);

// --- E. Cleanroom Main & Cryo Lab Doors (3-minute open timer) ---
fbDoor01(
    IN            := bDoor01_MainDoor,
    tPickupDelay  := T#3M,
    tDropoutDelay := T#5S
);

fbDoor02(
    IN            := bDoor02_CryoLabDoor,
    tPickupDelay  := T#3M,
    tDropoutDelay := T#5S
);

END_PROGRAM

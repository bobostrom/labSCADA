(* ==============================================================================
   PROGRAM: PLC_PRG
   DESCRIPTION: Main execution program for CODESYS Controller (Demo & Production).
                Configured with IVF Laboratory telemetry points, modular clinical
                equipment function blocks, and debounced pickup/dropout timing filters.
                OPC UA clients subscribe directly to the Function Block outputs
                (e.g. fbDewar1.rProcessTemp, fbDewar1.bAlarm, fbDewar1.bWarn).
                Simulation fault injection is encapsulated inside each Function Block
                (e.g. fbDewar1.bForceExcursion) and only active when bSimMode is TRUE.
   ============================================================================== *)
PROGRAM PLC_PRG
VAR
    (* --- System Heartbeat Blinker (Pure IEC 61131-3) --- *)
    {attribute 'symbol' := 'none'}
    tonBlink                : TON;
    {attribute 'symbol' := 'read'}
    bHeartbeat              : BOOL := FALSE;

    (* --- Analog Telemetry: Room Ambient Published over OPC UA --- *)
    {attribute 'symbol' := 'read'}
    rLabAmbientTemp         : REAL := 25.0;     (* Target ~25.0 °C *)

    (* --- Discrete Telemetry: Physical Door Contacts Published over OPC UA --- *)
    {attribute 'symbol' := 'read'}
    bDoor01                 : BOOL := FALSE;    (* FALSE = Closed, TRUE = Open *)
    {attribute 'symbol' := 'read'}
    bDoor02                 : BOOL := FALSE;    (* FALSE = Closed, TRUE = Open *)

    (* --- Discrete Hardware Inputs (Mapped from afoa-node00 750-341 via Modbus TCP) --- *)
    {attribute 'symbol' := 'none'}
    bIncubator01_RawContact : BOOL := FALSE;    (* DI 1 on afoa-node00 750-436 *)
    {attribute 'symbol' := 'none'}
    bIncubator02_RawContact : BOOL := FALSE;    (* DI 2 on afoa-node00 750-436 *)
    {attribute 'symbol' := 'none'}
    bCabinetDoor_RawContact : BOOL := FALSE;    (* DI 8 on afoa-node00 750-436 *)

    (* --- Encapsulated Clinical Equipment Function Blocks (Published over OPC UA) --- *)
    fbFridge                : FB_MedFridge;
    fbFreezer               : FB_MedFreezer;
    fbDewar1                : FB_Dewar;
    fbDewar2                : FB_Dewar;
    fbDewar3                : FB_Dewar;
    fbDewar4                : FB_Dewar;
    fbDewar5                : FB_Dewar;
    fbCabinet01             : FB_IncubatorCabinet;
    fbIncubator1            : FB_G210_Incubator;
    fbIncubator2            : FB_G210_Incubator;
    fbDoor01                : FB_PickupDropout;
    fbDoor02                : FB_PickupDropout;

    (* --- Ambient Room Drift Dynamics --- *)
    {attribute 'symbol' := 'none'}
    tonAmbientTick          : TON;
    {attribute 'symbol' := 'none'}
    iAmbientStep            : INT := 0;

    (* --- Master Simulation Control --- *)
    {attribute 'symbol' := 'readwrite'}
    bGlobalSimMode          : BOOL := TRUE;     (* TRUE = Demo Virtual Simulation; FALSE = Live Hardware Probes *)
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
    rRawTemp     := 3.5,
    rNominalTemp := 3.5,
    bSimMode     := bGlobalSimMode
);

// --- B. Medical Freezer (< -15.0°C, 3m pickup, 10s dropout) ---
fbFreezer(
    rRawTemp     := -20.0,
    rNominalTemp := -20.0,
    bSimMode     := bGlobalSimMode
);

// --- C. Cryogenic LN2 Dewars 1 - 5 (< -135.0°C, 30s pickup, 10s dropout) ---
fbDewar1(
    rRawTemp     := -150.0,
    rNominalTemp := -150.0,
    bSimMode     := bGlobalSimMode
);

fbDewar2(
    rRawTemp     := -150.0,
    rNominalTemp := -150.0,
    bSimMode     := bGlobalSimMode
);

fbDewar3(
    rRawTemp     := -150.0,
    rNominalTemp := -150.0,
    bSimMode     := bGlobalSimMode
);

fbDewar4(
    rRawTemp     := -150.0,
    rNominalTemp := -150.0,
    bSimMode     := bGlobalSimMode
);

fbDewar5(
    rRawTemp     := -150.0,
    rNominalTemp := -150.0,
    bSimMode     := bGlobalSimMode
);

// --- D. Incubator Cabinet 01 & Incubators (Muted when door open + 3m recovery grace) ---
fbCabinet01(
    bRawDoorContact     := bCabinetDoor_RawContact,
    bDoorNormallyClosed := TRUE,    (* TRUE = Contact closes at 0V when door is closed *)
    bSimMode            := bGlobalSimMode,
    tDoorAlarmDelay     := T#3M,    (* Alarm if cabinet door left open > 3 minutes *)
    tPostCloseGrace     := T#3M     (* Keep incubator alarms muted for 3 minutes after closing *)
);

fbIncubator1(
    bAlarmContact := bIncubator01_RawContact,
    bMute         := fbCabinet01.bIncubatorMute
);

fbIncubator2(
    bAlarmContact := bIncubator02_RawContact,
    bMute         := fbCabinet01.bIncubatorMute
);

// --- E. Facility Doors 01 & 02 (60-minute open timer) ---
fbDoor01(
    IN            := bDoor01,
    tPickupDelay  := T#60M,
    tDropoutDelay := T#5S
);

fbDoor02(
    IN            := bDoor02,
    tPickupDelay  := T#60M,
    tDropoutDelay := T#5S
);

END_PROGRAM

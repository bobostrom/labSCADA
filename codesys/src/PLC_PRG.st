(* ==============================================================================
   PROGRAM: PLC_PRG
   DESCRIPTION: Main execution program for CODESYS Controller.
                Includes:
                1. System Heartbeat LED blinker (500ms toggle)
                2. IVF Lab Telemetry Simulation (Fridges, Freezers, Cryo, Incubators)
                3. OPC UA ready symbols for Rapid SCADA integration
   ============================================================================== *)
PROGRAM PLC_PRG
VAR
    (* --- Heartbeat & LED Blinker --- *)
    tonBlinkTimer   : TON;
    bLedOutput      : BOOL := FALSE;    (* Map to physical GPIO in I/O Mapping, or monitor in SCADA *)
    tBlinkInterval  : TIME := T#500MS;  (* Half-period: 500ms ON, 500ms OFF = 1Hz *)
    udiCycleCount   : UDINT := 0;

    (* --- Emulated Telemetry: IVF Laboratory Temperatures --- *)
    rLabAmbient     : REAL := 21.5;     (* Cnl 101: Lab Ambient (Target ~21-22 C) *)
    rMedFridge      : REAL := 4.2;      (* Cnl 102: Med Fridge (Target ~4.0 C, Range 2 to 8 C) *)
    rMedFreezer     : REAL := -20.1;    (* Cnl 103: Med Freezer (Target ~ -20 C) *)
    rCryoTank01     : REAL := -195.4;   (* Cnl 125: Embryo Cryo Tank LN2 (Target ~ -196 C) *)
    rIncubator01Temp: REAL := 37.0;     (* Cnl 104: Benchtop Incubator 01 (Target 37.0 C) *)
    rIncubator02Temp: REAL := 37.1;     (* Cnl 105: Benchtop Incubator 02 (Target 37.0 C) *)

    (* --- Emulated Discrete Alarms & Doors --- *)
    bDoorFridgeOpen : BOOL := FALSE;    (* Cnl 121: Fridge Door Reed Switch *)
    bDoorFreezerOpen: BOOL := FALSE;    (* Cnl 122: Freezer Door Reed Switch *)
    bIncubator01Alm : BOOL := FALSE;    (* Cnl 123: Incubator 01 Alarm Dry Contact *)
    bIncubator02Alm : BOOL := FALSE;    (* Cnl 124: Incubator 02 Alarm Dry Contact *)

    (* --- Simulation Walkers --- *)
    tonSimTick      : TON;
    iSimStep        : INT := 0;
END_VAR

// ==============================================================================
// 1. SYSTEM HEARTBEAT BLINKER
// ==============================================================================
// Standard non-blocking IEC 61131-3 timer flip-flop
tonBlinkTimer(IN := NOT tonBlinkTimer.Q, PT := tBlinkInterval);

IF tonBlinkTimer.Q THEN
    bLedOutput := NOT bLedOutput;
    udiCycleCount := udiCycleCount + 1;
END_IF;


// ==============================================================================
// 2. IVF LAB TELEMETRY EMULATION (FOR TESTING OPC UA & SCADA)
// ==============================================================================
// Updates simulated values every 2 seconds with realistic minor drift
tonSimTick(IN := NOT tonSimTick.Q, PT := T#2S);

IF tonSimTick.Q THEN
    iSimStep := (iSimStep + 1) MOD 100;

    // Small subtle perturbations around clinical setpoints
    rLabAmbient      := 21.5 + 0.3 * SIN(TO_REAL(iSimStep) * 0.1);
    rMedFridge       := 4.1  + 0.4 * COS(TO_REAL(iSimStep) * 0.15);
    rMedFreezer      := -20.0 + 0.5 * SIN(TO_REAL(iSimStep) * 0.08);
    rIncubator01Temp := 37.0 + 0.08 * SIN(TO_REAL(iSimStep) * 0.2);
    rIncubator02Temp := 37.05 + 0.07 * COS(TO_REAL(iSimStep) * 0.25);
    rCryoTank01      := -195.5 + 0.2 * SIN(TO_REAL(iSimStep) * 0.05);
END_IF;

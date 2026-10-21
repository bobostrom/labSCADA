(* ==============================================================================
   PROGRAM: PLC_PRG
   DESCRIPTION: Main execution program for CODESYS Controller.
                Configured with IVF Laboratory telemetry points:
                1. System Heartbeat Blinker (500ms toggle for GPIO / verification)
                2. Lab Ambient Temperature (~25°C)
                3. Medical Fridge Temperature (~3°C)
                4. Medical Freezer Temperature (~ -20°C)
                5. Cryo Tank Temperature (~ -150°C)
                6. Door 01: Main Door (BOOL)
                7. Door 02: Cryo/Lab Door (BOOL)
                8. Incubator 01 Alarm (BOOL)
                9. Incubator 02 Alarm (BOOL)
   ============================================================================== *)
PROGRAM PLC_PRG
VAR
    (* --- Heartbeat & LED Blinker --- *)
    tonBlinkTimer       : TON;
    bLedOutput          : BOOL := FALSE;    (* Toggles ON/OFF every 500ms (1 Hz) *)
    tBlinkInterval      : TIME := T#500MS;  (* 500ms ON / 500ms OFF *)
    udiCycleCount       : UDINT := 0;

    (* --- Analog Telemetry: Temperatures --- *)
    rLabAmbientTemp     : REAL := 25.0;     (* Target ~25.0 °C *)
    rMedFridgeTemp      : REAL := 3.0;      (* Target ~3.0 °C *)
    rMedFreezerTemp     : REAL := -20.0;    (* Target ~ -20.0 °C *)
    rCryoTankTemp       : REAL := -150.0;   (* Target ~ -150.0 °C *)

    (* --- Discrete Telemetry: Doors & Alarms --- *)
    bDoor01_MainDoor    : BOOL := FALSE;    (* Door 01 (Main Door): FALSE = Closed, TRUE = Open *)
    bDoor02_CryoLabDoor : BOOL := FALSE;    (* Door 02 (Cryo/Lab Door): FALSE = Closed, TRUE = Open *)
    bIncubator01_Alarm  : BOOL := FALSE;    (* Incubator 01 Alarm: FALSE = Normal, TRUE = Alarm *)
    bIncubator02_Alarm  : BOOL := FALSE;    (* Incubator 02 Alarm: FALSE = Normal, TRUE = Alarm *)

    (* --- Simulation Controls --- *)
    tonSimTick          : TON;
    iSimStep            : INT := 0;
    bSimulateDynamics   : BOOL := TRUE;     (* Set to FALSE to hold exact static setpoints *)
END_VAR

// ==============================================================================
// 1. SYSTEM HEARTBEAT BLINKER
// ==============================================================================
// Standard non-blocking IEC 61131-3 timer flip-flop
// Must be called unconditionally outside IF blocks to properly self-reset
tonBlinkTimer(IN := NOT tonBlinkTimer.Q, PT := tBlinkInterval);

IF tonBlinkTimer.Q THEN
    bLedOutput := NOT bLedOutput;
    udiCycleCount := udiCycleCount + 1;
END_IF;


// ==============================================================================
// 2. IVF LAB TELEMETRY SIMULATION
// ==============================================================================
// Generates realistic subtle thermal drifts around clinical setpoints
tonSimTick(IN := NOT tonSimTick.Q, PT := T#1S);

IF tonSimTick.Q AND bSimulateDynamics THEN
    iSimStep := (iSimStep + 1) MOD 360;

    // Lab Ambient: smooth drift around 25.0 °C (24.7 °C to 25.3 °C)
    rLabAmbientTemp     := 25.0 + 0.3 * SIN(TO_REAL(iSimStep) * 0.05);

    // Medical Fridge: refrigeration cycle around 3.0 °C (2.6 °C to 3.4 °C)
    rMedFridgeTemp      := 3.0  + 0.4 * COS(TO_REAL(iSimStep) * 0.08);

    // Medical Freezer: compressor cycle around -20.0 °C (-20.6 °C to -19.4 °C)
    rMedFreezerTemp     := -20.0 + 0.6 * SIN(TO_REAL(iSimStep) * 0.06);

    // Cryo Tank: vapor phase LN2 thermal dynamics around -150.0 °C (-150.8 °C to -149.2 °C)
    rCryoTankTemp       := -150.0 + 0.8 * COS(TO_REAL(iSimStep) * 0.03);
END_IF;

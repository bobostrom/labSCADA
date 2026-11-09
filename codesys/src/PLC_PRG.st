(* ==============================================================================
   PROGRAM: PLC_PRG
   DESCRIPTION: Main execution program for CODESYS Controller (Demo & Production).
                Configured with IVF Laboratory telemetry points, modular clinical
                equipment function blocks, and debounced pickup/dropout timing filters.
                OPC UA clients subscribe directly to the Function Block outputs
                (e.g. fbDewar1.rProcessTemp, fbColdStorage.rFridgeTemp, fbColdStorage.rFreezerTemp).
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
    rLabAmbientTemp         : REAL := 25.0;     (* Target ~25.0 °C (derived from fbColdStorage.rAmbientTemp) *)

    (* --- Encapsulated Clinical Equipment Function Blocks (Published over OPC UA) --- *)
    fbColdStorage           : FB_MedColdStorage; (* Live Wireless Node Slot 2: Fridge, Freezer & Ambient *)
    fbDewar1                : FB_Dewar;          (* Live Wireless Node Slot 1: Cryo LN2 Dewar 1 *)
    fbDewar2                : FB_Dewar;
    fbDewar3                : FB_Dewar;
    fbDewar4                : FB_Dewar;
    fbDewar5                : FB_Dewar;
    fbCabinet01             : FB_IncubatorCabinet;
    fbIncubator1            : FB_G210_Incubator;
    fbIncubator2            : FB_G210_Incubator;
    fbDoor01                : FB_FacilityDoor;
    fbDoor02                : FB_FacilityDoor;
    fbUPS01                 : FB_APC_SmartUPS;
END_VAR

// ==============================================================================
// 1. SYSTEM HEARTBEAT BLINKER (1 Hz)
// ==============================================================================
tonBlink(IN := NOT tonBlink.Q, PT := T#500MS);
IF tonBlink.Q THEN
    bHeartbeat := NOT bHeartbeat;
END_IF;

// ==============================================================================
// 2. MEDICAL COLD STORAGE & AMBIENT (Live Wireless Node Slot 2 via Modbus RTU COM1)
// ==============================================================================
// Modbus RTU I/O mapped directly into fbColdStorage (Holding Registers 0..9)
fbColdStorage();
rLabAmbientTemp := fbColdStorage.rAmbientTemp;

// ==============================================================================
// 3. CRYOGENIC LN2 DEWARS 1 - 5 (< -135.0°C, 30s pickup, 10s dropout)
// ==============================================================================
// Dewar 1 is live wireless sensor node (I/O mapped directly from Modbus RTU COM1 Slot 1)
fbDewar1();

// Dewars 2 - 5 (Unassigned slots default to sentinel -9999 / disconnected)
fbDewar2();
fbDewar3();
fbDewar4();
fbDewar5();

// ==============================================================================
// 4. INCUBATOR CABINET 01 & CHAMBER INCUBATORS
// ==============================================================================
fbCabinet01();

fbIncubator1(
    bMute := fbCabinet01.bIncubatorMute
);

fbIncubator2(
    bMute := fbCabinet01.bIncubatorMute
);

// ==============================================================================
// 5. FACILITY DOORS 01 & 02 (60-minute open timer)
// ==============================================================================
fbDoor01();
fbDoor02();

// ==============================================================================
// 6. FACILITY UPS POWER SUBSYSTEM (demo-ups via Modbus TCP)
// ==============================================================================
// Modbus TCP I/O is mapped directly into fbUPS01 member inputs (wStatusWord, wBatteryPct, etc.)
fbUPS01(
    tPowerLossDelay     := T#10S,   (* 10-second debounce for utility flickers *)
    wLowBatteryLimit    := 20,      (* Critical alarm threshold at 20% *)
    wLowRuntimeLimitMin := 15       (* Critical alarm threshold at 15 min *)
);

END_PROGRAM

(* ==============================================================================
   PROGRAM: PLC_PRG
   DESCRIPTION: Main execution program for CODESYS Controller (Demo & Production).
                Configured with IVF Laboratory telemetry points, modular clinical
                equipment function blocks, and debounced pickup/dropout timing filters.
                OPC UA clients subscribe directly to the Function Block outputs
                (e.g. fbDewar1.rProcessTemp, fbColdStorage.fbFridge.rProcessTemp, fbColdStorage.fbFreezer.rProcessTemp).
   ============================================================================== *)
PROGRAM PLC_PRG
VAR
	fbRandomNumber: FB_RandomGenerator;
    (* --- System Heartbeat Blinker (Pure IEC 61131-3) --- *)
    tonBlink: TON;
    bHeartbeat: BOOL := FALSE;

    (* --- Analog Telemetry: Room Ambient Published over OPC UA --- *)
    rLabAmbientTemp: REAL := 25.0; (* Target ~25.0 °C (derived from fbColdStorage.rAmbientTemp) *)

    (* --- Encapsulated Clinical Equipment Function Blocks (Published over OPC UA) --- *)
    fbColdStorage: FB_MedColdStorage; (* Live Wireless Node Slot 2: Fridge, Freezer & Ambient *)
    fbDewar1: FB_Dewar; (* Live Wireless Node Slot 1: Cryo LN2 Dewar 1 *)
    fbDewar2: FB_Dewar;
    fbDewar3: FB_Dewar;
    fbDewar4: FB_Dewar;
    fbDewar5: FB_Dewar;
    fbCabinet01: FB_IncubatorCabinet;
    fbIncubator1: FB_G210_Incubator;
    fbIncubator2: FB_G210_Incubator;
    fbDoor01: FB_FacilityDoor;
    fbDoor02: FB_FacilityDoor;
    fbUPS01: FB_APC_SmartUPS;
END_VAR


// ==============================================================================
// 1. SYSTEM HEARTBEAT BLINKER (1 Hz)
// ==============================================================================
tonBlink(IN := NOT tonBlink.Q, PT := T#500ms);
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
// --- TEMPORARY TEST OVERRIDE: Simulate -150.0°C ---
fbRandomNumber(bExecute := TRUE, diMin := - 1550, diMax := - 1500);
fbDewar1.wRawTempX10 := TO_WORD(fbRandomNumber.diResult);
// fbDewar1.wRawTempX10 := TO_WORD(-1500);
fbDewar1.uiRawFaultCode := 0;
fbDewar1.wRawStatusFlags := 16#0001; (* Bit 0 = Online *)
fbDewar1.uiRawAgeSec := 0;
fbDewar1();
fbRandomNumber(bExecute := TRUE, diMin := - 1550, diMax := - 1500);
fbDewar2.wRawTempX10 := TO_WORD(fbRandomNumber.diResult);
// fbDewar2.wRawTempX10 := TO_WORD(-1550);
fbDewar2.uiRawFaultCode := 0;
fbDewar2.wRawStatusFlags := 16#0001; (* Bit 0 = Online *)
fbDewar2.uiRawAgeSec := 0;
fbDewar2();
// Dewars 3 - 5 remain unmapped spare slots
fbDewar3();
fbDewar4();
fbDewar5();

// ==============================================================================
// 4. INCUBATOR CABINET 01 & CHAMBER INCUBATORS
// ==============================================================================
fbCabinet01.bDoorClosed := TRUE;
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
fbDoor01.bDoorClosed := TRUE;
fbDoor01();
fbDoor02.bDoorClosed := TRUE;
fbDoor02();

// ==============================================================================
// 6. FACILITY UPS POWER SUBSYSTEM (demo-ups via Modbus TCP)
// ==============================================================================
// Modbus TCP I/O is mapped directly into fbUPS01 member inputs (wStatusWord, wBatteryPct, etc.)
fbUPS01(
    tPowerLossDelay := T#10s, (* 10-second debounce for utility flickers *)
    wLowBatteryLimit := 20, (* Critical alarm threshold at 20% *)
    wLowRuntimeLimitMin := 15 (* Critical alarm threshold at 15 min *)
);

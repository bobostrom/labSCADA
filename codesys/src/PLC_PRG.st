(* ==============================================================================
   PROGRAM: PLC_PRG
   DESCRIPTION: Main execution program for AFOA WAGO 750-8212 CODESYS Controller.
                Updated for Lares_Clinical_SCADA library v1.0.0.26:
                - Hierarchical fbColdStorage (Fridge, Freezer, Cleanroom Ambient)
                - Dewars 2 - 5 (Dewar 1 discontinued; bIsWireless := FALSE for now)
                - Facility Doors (FB_FacilityDoor) & Incubator Cabinet (FB_IncubatorCabinet)
                  standardized on direct fail-safe NC wiring (bDoorClosed: TRUE = Closed)
                - K-Systems G210 Incubators & APC Smart-UPS
   ============================================================================== *)
PROGRAM PLC_PRG
VAR
    (* --- System Heartbeat Blinker (Pure IEC 61131-3) --- *)
    tonBlink                : TON;
    bHeartbeat              : BOOL := FALSE;
    (* --- Analog Telemetry: Room Ambient Published over OPC UA --- *)
    rLabAmbientTemp         : REAL := 25.0;     (* Derived from fbColdStorage.rAmbientTemp *)
    (* --- Encapsulated Clinical Equipment Function Blocks (Published over OPC UA) --- *)
    fbColdStorage           : FB_MedColdStorage; (* Fridge, Freezer & Cleanroom Ambient *)
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
    fbUPS02                 : FB_APC_SmartUPS;
    {attribute 'symbol' := 'none'}
    awIncuUpsRegs           : ARRAY[0..19] OF WORD; (* AP9640 NMC3 HR[0..19] *)
    {attribute 'symbol' := 'none'}
    wIncuUpsStatusWord      : WORD := 0;
END_VAR
// ==============================================================================
// 1. SYSTEM HEARTBEAT BLINKER (1 Hz)
// ==============================================================================
tonBlink(IN := NOT tonBlink.Q, PT := T#500MS);
IF tonBlink.Q THEN
    bHeartbeat := NOT bHeartbeat;
END_IF;
// ==============================================================================
// 2. MEDICAL COLD STORAGE & AMBIENT (1.0–8.0°C Fridge, < -15.0°C Freezer, 20–27°C Ambient)
// ==============================================================================
// Standby placeholder temps until wireless/physical probes are installed
// (Unmapped wRaw*TempX10 defaults to 16#D8F0 = -999.0°C Probe Fault)
fbColdStorage(
//     wRawFridgeTempX10  := TO_WORD(35),          (* 3.5 °C *)
//     wRawFreezerTempX10 := TO_WORD(-200),        (* -20.0 °C *)
//     wRawAmbientTempX10 := TO_WORD(250),         (* 25.0 °C *)
//     bIsWireless        := TRUE
);
rLabAmbientTemp := fbColdStorage.rAmbientTemp;
// ==============================================================================
// 3. CRYOGENIC LN2 DEWARS 2 - 5 (< -135.0°C, 30s pickup, 10s dropout)
// ==============================================================================
// Dewar 1 discontinued. Dewars 2-5 use standby placeholders until wireless nodes arrive.
// fbDewar2.wRawTempX10 := fbDewar2.wRawTempX10 - 1700;
fbDewar2(
//     wRawTempX10 := TO_WORD(-1500),              (* -150.0 °C *)
// 	wRawTempX10 : TO_WORD(wRawTemp - 1700),
//     bIsWireless := TRUE
);
fbDewar3(
    bIsWireless := TRUE
);
fbDewar4(
    wRawTempX10 := TO_WORD(-1500),
    bIsWireless := FALSE
);
fbDewar5(
    wRawTempX10 := TO_WORD(-1500),
    bIsWireless := FALSE
);
// ==============================================================================
// 4. INCUBATOR CABINET 01 & G210 INCUBATORS (Muted when door open + 3m grace)
// ==============================================================================
// Direct I/O mapping: afoa-node00 DI -> fbCabinet01.bDoorClosed (TRUE = Closed)
// Temperature/fan inputs stay at defaults (24.5°C / 28.0°C setpoint) until sensors/fan are wired.
fbCabinet01(
	//TODO: switch wiring on door
	//bDoorClosed := TRUE,
    tDoorAlarmDelay := T#3M,
    tPostCloseGrace := T#3M
);
fbIncubator1(
    bMute := fbCabinet01.bIncubatorMute
);
fbIncubator2(
    bMute := fbCabinet01.bIncubatorMute
);
// ==============================================================================
// 5. CLEANROOM DOORS 01 & 02 (60-minute open timer)
// ==============================================================================
// Direct I/O mapping: K-Bus DI -> fbDoor01.bDoorClosed / fbDoor02.bDoorClosed (TRUE = Closed)
fbDoor01(
    tOpenAlarmDelay := T#60M,
    tDropoutDelay   := T#5S
);
fbDoor02(
    tOpenAlarmDelay := T#60M,
    tDropoutDelay   := T#5S
);
// ==============================================================================
// 6. FACILITY UPS POWER SUBSYSTEM (APC Smart-UPS via ups-modbus-bridge)
// ==============================================================================
fbUPS01(
    tPowerLossDelay     := T#10S,
    wLowBatteryLimit    := 20,
    wLowRuntimeLimitMin := 15
);
// 7. INCUBATOR CABINET 01 UPS (afoa-incu-ups, APC Smart-UPS 1500 AP9640 @ 192.168.88.250)
// Native AP9640 Modbus HR[0..19]: HR[3]=0x0008(OnLine)/0x0010(OnBatt)/0x0040(LowBatt),
// HR[5]=BattPct(%), HR[6]=Runtime(min), HR[14]=LineVoltage(VAC), HR[19]=LoadPct(%)
wIncuUpsStatusWord := 0;
IF (awIncuUpsRegs[3] AND 16#0008) <> 0 THEN
    wIncuUpsStatusWord := wIncuUpsStatusWord OR 16#0001;
END_IF;
IF (awIncuUpsRegs[3] AND 16#0010) <> 0 THEN
    wIncuUpsStatusWord := wIncuUpsStatusWord OR 16#0002;
END_IF;
IF (awIncuUpsRegs[3] AND 16#0040) <> 0 THEN
    wIncuUpsStatusWord := wIncuUpsStatusWord OR 16#0010;
END_IF;
fbUPS02(
    wStatusWord         := wIncuUpsStatusWord,
    wBatteryPct         := awIncuUpsRegs[5],
    wLineVoltageX10     := awIncuUpsRegs[14] * 10,
    wLoadPct            := awIncuUpsRegs[19],
    wRuntimeMin         := awIncuUpsRegs[6],
    tPowerLossDelay     := T#10S,
    wLowBatteryLimit    := 20,
    wLowRuntimeLimitMin := 15
);
END_PROGRAM

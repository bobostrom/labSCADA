(* ==============================================================================
   FUNCTION BLOCK: FB_Dewar
   DESCRIPTION: Encapsulated clinical monitoring block for Liquid Nitrogen (LN2)
                cryogenic storage vessels (dewars / freezers).
                - Scaled raw integer input (iRawTempX10 / 10.0 -> °C)
                - High threshold alarm with hysteresis & debounced pickup timing
                - Clinical fault supervision (Open circuit, wiring short, comms loss)
                - High-temperature excursion alarm gated off during hardware faults
                - Wireless cleanroom health diagnostics (Battery, RSSI, Watchdog, Faults)
   ============================================================================== *)
FUNCTION_BLOCK FB_Dewar
VAR_INPUT
    (* --- Operational Alarm Thresholds & Delays --- *)
    rHighTrip           : REAL := -135.0;   (* Critical specimen danger limit (°C) *)
    rHysteresis         : REAL := 5.0;      (* Reset deadband (°C) *)
    tPickupDelay        : TIME := T#30S;    (* Sustained warm excursion required to trip *)
    tDropoutDelay       : TIME := T#10S;    (* Clean fill required to reset *)

    (* --- 8 Modbus Holding Registers (Direct from Bridge Slot 1) --- *)
    wRawTempX10         : WORD := 16#D8F0;  (* Offset 0: Dewar scaled temp * 10 (-1954 = -195.4 °C, -9999 = Sentinel) *)
    uiRawBatteryMv      : UINT := 3850;     (* Offset 1: Battery health in millivolts *)
    uiRawFaultCode      : UINT := 0;        (* Offset 2: Probe fault (0=OK, 1=Open, 2=GND, 3=VCC, 4=Hardware Error) *)
    wRawRSSI            : WORD := 16#FFCE;  (* Offset 3: Wireless link margin in dBm (-50 = 16#FFCE) *)
    wRawSeqLow          : WORD := 0;        (* Offset 4: Sequence counter low word *)
    wRawSeqHigh         : WORD := 0;        (* Offset 5: Sequence counter high word *)
    uiRawAgeSec         : UINT := 0;        (* Offset 6: Telemetry age in seconds *)
    wRawStatusFlags     : WORD := 16#0001;  (* Offset 7: Bit 0=Online, Bit 1=LowBatt, Bit 2=CommLoss, Bit 3=AccessMode *)
    bIsWireless         : BOOL := TRUE;     (* TRUE = Enable wireless diagnostics *)
    tCommLossTimeout    : TIME := T#60S;    (* Watchdog comms loss alarm threshold *)

    (* --- Interactive Operator Commands (from Kiosk UI or OPC UA) --- *)
    bCmdSetAccessMode   : BOOL := FALSE;    (* TRUE pulse: Activate Access Mode (Alarms paused 30 min) *)
    bCmdCancelAccessMode: BOOL := FALSE;    (* TRUE pulse: Cancel Access Mode immediately *)
END_VAR
VAR_OUTPUT
    rProcessTemp        : REAL := -999.0;   (* Published process temperature to SCADA (°C) *)
    bAlarm              : BOOL := FALSE;    (* Priority 2 Emergency Temperature Alarm flag *)
    bWarn               : BOOL := FALSE;    (* Pre-alarm pickup delay warning flag *)
    rBatteryVolts       : REAL := 3.85;     (* Published battery voltage (V) *)
    bLowBattery         : BOOL := FALSE;    (* Low battery warning flag (< 3.4V) *)
    iRSSI               : INT := -50;       (* Published wireless link margin (dBm) *)
    bCommLoss           : BOOL := FALSE;    (* Comms loss watchdog alarm *)
    bProbeFault         : BOOL := TRUE;     (* Physical probe disconnected or shorted (defaults TRUE on cold boot) *)
    uiFaultCode         : UINT := 0;        (* Published probe fault reason (0=OK, 1=Open, 2=GND, 3=VCC) *)
    uiAgeSec            : UINT := 0;        (* Telemetry age in seconds *)
    bAccessMode         : BOOL := FALSE;    (* Access Mode active - Alarms paused 30 min for tank maintenance *)

    (* --- Modbus Command Outputs (Mapped to Bridge Holding Regs 10 & 11) --- *)
    wCommandMailboxOut  : WORD := 0;        (* Offset 10: 5 = SetAccessMode *)
    wCommandParamOut    : WORD := 0;        (* Offset 11: 30 = 30 minutes, 0 = Cancel *)
END_VAR
VAR
    iTempX10            : INT;
    fbAlarmEval         : FB_AnalogAlarm;
    wActiveCmdCode      : WORD := 0;
    wActiveCmdParam     : WORD := 0;
    bPrevSetAccess      : BOOL := FALSE;
    bPrevCancelAccess   : BOOL := FALSE;
    tonCmdPulse         : TON;
END_VAR
// --- implementation ---
// ==============================================================================
// 1. HARDWARE HEALTH & TELEMETRY DECODING
// ==============================================================================
// Explicitly cast Modbus unsigned WORD inputs to signed two's complement INT
iTempX10 := TO_INT(wRawTempX10);

IF bIsWireless THEN
    rBatteryVolts := TO_REAL(uiRawBatteryMv) / 1000.0;
    bLowBattery   := (uiRawBatteryMv < 3400) OR (wRawStatusFlags.1);
    iRSSI         := TO_INT(wRawRSSI);
    uiAgeSec      := uiRawAgeSec;
    uiFaultCode   := uiRawFaultCode;

    // Probe fault if hardware reported fault code or value is sentinel (<= -273°C or >= 900°C)
    bProbeFault   := (uiRawFaultCode <> 0) OR (iTempX10 <= -2730) OR (iTempX10 >= 9000);

    // Watchdog comms loss if bridge flagged or age exceeds timeout
    bCommLoss     := (NOT wRawStatusFlags.0) OR (wRawStatusFlags.2) OR (uiRawAgeSec > (TIME_TO_UINT(tCommLossTimeout) / 1000));

    // Access Mode Active (Bit 3 of status flags: Alarms paused 30 min)
    bAccessMode   := wRawStatusFlags.3;
ELSE
    rBatteryVolts := 0.0;
    bLowBattery   := FALSE;
    iRSSI         := 0;
    bCommLoss     := FALSE;
    uiFaultCode   := 0;
    bProbeFault   := (iTempX10 <= -2730) OR (iTempX10 >= 9000);
    uiAgeSec      := 0;
    bAccessMode   := FALSE;
END_IF;

// ==============================================================================
// 2. TEMPERATURE SENTINEL MAPPING
// ==============================================================================
// If probe is faulted or comms lost, output standard invalid sentinel (-999.0 °C)
IF bProbeFault OR bCommLoss THEN
    rProcessTemp := -999.0;
ELSE
    rProcessTemp := TO_REAL(iTempX10) / 10.0;
END_IF;

// ==============================================================================
// 3. CLINICAL ALARM EVALUATION (Pickup / Dropout & Hysteresis)
// ==============================================================================
// Thermal excursion alarms are only evaluated when sensor data is valid and not in access mode
fbAlarmEval(
    rVal          := rProcessTemp,
    bEnableHigh   := NOT (bProbeFault OR bCommLoss OR bAccessMode),
    rHighPickup   := rHighTrip,
    rHighDropout  := rHighTrip - rHysteresis,
    bEnableLow    := FALSE,
    tPickupDelay  := tPickupDelay,
    tDropoutDelay := tDropoutDelay
);

// If in Access Mode, clamp alarms and warnings to FALSE immediately (bypassing dropout timer)
IF bAccessMode THEN
    bAlarm := FALSE;
    bWarn  := FALSE;
ELSE
    bAlarm := fbAlarmEval.bAlarm;
    bWarn  := fbAlarmEval.bWarn;
END_IF;

// ==============================================================================
// 4. SUPERVISORY COMMAND DISPATCH (Downlink to Bridge & Physical Node)
// ==============================================================================
// Latch active command for 2.0s so Modbus cyclic write task reliably transmits to Bridge
IF bCmdSetAccessMode AND NOT bPrevSetAccess THEN
    wActiveCmdCode    := 5;     // 5 = SetAccessMode
    wActiveCmdParam   := 30;    // 30 minutes
    bCmdSetAccessMode := FALSE;
ELSIF bCmdCancelAccessMode AND NOT bPrevCancelAccess THEN
    wActiveCmdCode       := 5;  // 5 = SetAccessMode
    wActiveCmdParam      := 0;  // 0 = Cancel / Normal Mode
    bCmdCancelAccessMode := FALSE;
END_IF;

bPrevSetAccess    := bCmdSetAccessMode;
bPrevCancelAccess := bCmdCancelAccessMode;

tonCmdPulse(IN := (wActiveCmdCode > 0), PT := T#2000MS);
IF tonCmdPulse.Q THEN
    wActiveCmdCode  := 0;
    wActiveCmdParam := 0;
END_IF;

wCommandMailboxOut := wActiveCmdCode;
wCommandParamOut   := wActiveCmdParam;
END_FUNCTION

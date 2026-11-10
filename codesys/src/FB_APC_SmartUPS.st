(* ==============================================================================
   FUNCTION BLOCK: FB_APC_SmartUPS
   DESCRIPTION: Encapsulated clinical monitoring block for UPS Power Systems
                following the Schneider Electric / APC Smart-UPS Modbus Register Map
                (AN-176 / 990-9840).
                - Supervised Utility Grid Power Loss (Generator Dispatch)
                - Battery State of Charge & Remaining Runtime Monitoring
                - Low Battery Reserve Emergency Escalation
                - Beeper Mute / Silence Supervisory Command Control
   ============================================================================== *)
FUNCTION_BLOCK FB_APC_SmartUPS
VAR_INPUT
    wStatusWord         : WORD := 16#0001;  (* Register 40001: Bit 0=Online, Bit 1=On Battery, Bit 4=Low Battery *)
    wBatteryPct         : WORD := 100;     (* Register 40002: Battery Charge (0-100%) *)
    wRuntimeSec         : WORD := 0;       (* Register 40003: Runtime in seconds *)
    wLineVoltageX10     : WORD := 1200;    (* Register 40004: Line Voltage * 10 (1200 = 120.0 V) *)
    wLoadPct            : WORD := 0;       (* Register 40005: Inverter Load (0-100%) *)
    wRuntimeMin         : WORD := 60;      (* Register 40007: Runtime in minutes *)
    wBeeperStatus       : WORD := 1;       (* Register 40008: 1=Enabled, 2=Muted, 3=Disabled *)

    (* --- Interactive Operator Commands (from Kiosk UI or PLC) --- *)
    bCmdMuteBeeper      : BOOL := FALSE;   (* TRUE pulse: Temporarily mute beeper for current power loss *)
    bCmdDisableBeeper   : BOOL := FALSE;   (* TRUE pulse: Disable beeper speaker *)
    bCmdEnableBeeper    : BOOL := FALSE;   (* TRUE pulse: Enable beeper speaker *)

    tPowerLossDelay     : TIME := T#10S;   (* Debounce filter to ignore momentary utility grid flickers *)
    wLowBatteryLimit    : WORD := 20;      (* Low battery alarm threshold (%) *)
    wLowRuntimeLimitMin : WORD := 15;      (* Low runtime alarm threshold (minutes) *)
END_VAR
VAR_OUTPUT
    bOnline             : BOOL := TRUE;    (* TRUE = Grid utility power is normal *)
    bOnBattery          : BOOL := FALSE;   (* TRUE = Running on battery inverter *)
    bAlarmPowerLost     : BOOL := FALSE;   (* Priority 2: Utility grid dropped -> Manual generator required *)
    bAlarmLowBattery    : BOOL := FALSE;   (* Priority 1: Battery reserve critically low *)
    rBatteryPct         : REAL := 100.0;   (* Battery % (0.0 - 100.0) *)
    rLineVoltage        : REAL := 120.0;   (* Utility line voltage in Volts RMS *)
    rRuntimeMinutes     : REAL := 60.0;    (* Estimated remaining runtime in minutes *)
    rLoadPct            : REAL := 0.0;     (* Current load percentage *)
    bBeeperMuted        : BOOL := FALSE;   (* Beeper is currently muted *)
    bBeeperDisabled     : BOOL := FALSE;   (* Beeper is disabled *)

    (* --- Modbus Command Output (Mapped to Holding Register 40010 / Offset 9) --- *)
    wCommandOut         : WORD := 0;       (* 1=Mute, 2=Disable, 3=Enable *)
END_VAR
VAR
    fbFilterPowerLoss   : FB_PickupDropout;
    tonCmdPulse         : TON;
    wActiveCmd          : WORD := 0;
    bPrevMute           : BOOL := FALSE;
    bPrevDisable        : BOOL := FALSE;
    bPrevEnable         : BOOL := FALSE;
END_VAR

// 1. DECODE APC SMART-UPS STATUS WORD (Register 40001)
// Bit 0 = State Online (Grid OK)
// Bit 1 = State On Battery (Power Failure)
// Bit 4 = Low Battery
bOnline    := (wStatusWord AND 16#0001) <> 0;
bOnBattery := (wStatusWord AND 16#0002) <> 0;

// 2. CONVERT RAW TELEMETRY TO ENGINEERING UNITS
rBatteryPct     := WORD_TO_REAL(wBatteryPct);
rLineVoltage    := WORD_TO_REAL(wLineVoltageX10) / 10.0;
rLoadPct        := WORD_TO_REAL(wLoadPct);

// Beeper status
bBeeperMuted    := (wBeeperStatus = 2);
bBeeperDisabled := (wBeeperStatus = 3);

// Calculate runtime in minutes (prefer wRuntimeMin if non-zero, else wRuntimeSec / 60)
IF wRuntimeMin > 0 THEN
    rRuntimeMinutes := WORD_TO_REAL(wRuntimeMin);
ELSIF wRuntimeSec > 0 THEN
    rRuntimeMinutes := WORD_TO_REAL(wRuntimeSec) / 60.0;
ELSE
    rRuntimeMinutes := 0.0;
END_IF;

// 3. DEBOUNCED UTILITY POWER LOSS ALARM (Generator Dispatch)
// Ignores 1-2 second lightning flickers, trips after sustained outage (tPowerLossDelay)
fbFilterPowerLoss(
    IN            := bOnBattery,
    tPickupDelay  := tPowerLossDelay,
    tDropoutDelay := T#5S
);
bAlarmPowerLost := fbFilterPowerLoss.Q;

// 4. CRITICAL LOW BATTERY ALARM
// Triggers if battery % drops below limit OR runtime drops below critical threshold while on battery
IF bOnBattery AND ((wBatteryPct <= wLowBatteryLimit) OR (rRuntimeMinutes <= WORD_TO_REAL(wLowRuntimeLimitMin))) THEN
    bAlarmLowBattery := TRUE;
ELSE
    bAlarmLowBattery := FALSE;
END_IF;

// 5. BEEPER COMMAND EXECUTION (Pulsed Output to Modbus Register 40010)
// Latch active command for 1.5s so asynchronous Modbus cyclic task reliably transmits write
IF bCmdMuteBeeper AND NOT bPrevMute THEN
    wActiveCmd := 1;       // 1 = Mute
    bCmdMuteBeeper := FALSE;
ELSIF bCmdDisableBeeper AND NOT bPrevDisable THEN
    wActiveCmd := 2;       // 2 = Disable
    bCmdDisableBeeper := FALSE;
ELSIF bCmdEnableBeeper AND NOT bPrevEnable THEN
    wActiveCmd := 3;       // 3 = Enable
    bCmdEnableBeeper := FALSE;
END_IF;

bPrevMute    := bCmdMuteBeeper;
bPrevDisable := bCmdDisableBeeper;
bPrevEnable  := bCmdEnableBeeper;

tonCmdPulse(IN := (wActiveCmd > 0), PT := T#1500MS);
IF tonCmdPulse.Q THEN
    wActiveCmd := 0;
END_IF;

wCommandOut := wActiveCmd;

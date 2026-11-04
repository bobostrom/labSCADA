(* ==============================================================================
   FUNCTION BLOCK: FB_APC_SmartUPS
   DESCRIPTION: Encapsulated clinical monitoring block for UPS Power Systems
                following the Schneider Electric / APC Smart-UPS Modbus Register Map
                (AN-176 / 990-9840).
                - Supervised Utility Grid Power Loss (Generator Dispatch)
                - Battery State of Charge & Remaining Runtime Monitoring
                - Low Battery Reserve Emergency Escalation
   ============================================================================== *)
FUNCTION_BLOCK FB_APC_SmartUPS
VAR_INPUT
    {attribute 'symbol' := 'readwrite'}
    wStatusWord         : WORD := 16#0001;  (* Register 40001: Bit 0=Online, Bit 1=On Battery, Bit 4=Low Battery *)
    {attribute 'symbol' := 'readwrite'}
    wBatteryPct         : WORD := 100;     (* Register 40002: Battery Charge (0-100%) *)
    {attribute 'symbol' := 'readwrite'}
    wRuntimeSec         : WORD := 0;       (* Register 40003: Runtime in seconds *)
    {attribute 'symbol' := 'readwrite'}
    wLineVoltageX10     : WORD := 1200;    (* Register 40004: Line Voltage * 10 (1200 = 120.0 V) *)
    {attribute 'symbol' := 'readwrite'}
    wLoadPct            : WORD := 0;       (* Register 40005: Inverter Load (0-100%) *)
    {attribute 'symbol' := 'readwrite'}
    wRuntimeMin         : WORD := 60;      (* Register 40007: Runtime in minutes *)

    {attribute 'symbol' := 'none'}
    tPowerLossDelay     : TIME := T#10S;   (* Debounce filter to ignore momentary utility grid flickers *)
    {attribute 'symbol' := 'none'}
    wLowBatteryLimit    : WORD := 20;      (* Low battery alarm threshold (%) *)
    {attribute 'symbol' := 'none'}
    wLowRuntimeLimitMin : WORD := 15;      (* Low runtime alarm threshold (minutes) *)
END_VAR
VAR_OUTPUT
    {attribute 'symbol' := 'read'}
    bOnline             : BOOL := TRUE;    (* TRUE = Grid utility power is normal *)
    {attribute 'symbol' := 'read'}
    bOnBattery          : BOOL := FALSE;   (* TRUE = Running on battery inverter *)
    {attribute 'symbol' := 'read'}
    bAlarmPowerLost     : BOOL := FALSE;   (* Priority 2: Utility grid dropped -> Manual generator required *)
    {attribute 'symbol' := 'read'}
    bAlarmLowBattery    : BOOL := FALSE;   (* Priority 1: Battery reserve critically low *)
    {attribute 'symbol' := 'read'}
    rBatteryPct         : REAL := 100.0;   (* Battery % (0.0 - 100.0) *)
    {attribute 'symbol' := 'read'}
    rLineVoltage        : REAL := 120.0;   (* Utility line voltage in Volts RMS *)
    {attribute 'symbol' := 'read'}
    rRuntimeMinutes     : REAL := 60.0;    (* Estimated remaining runtime in minutes *)
    {attribute 'symbol' := 'read'}
    rLoadPct            : REAL := 0.0;     (* Current load percentage *)
END_VAR
VAR
    {attribute 'symbol' := 'none'}
    fbFilterPowerLoss   : FB_PickupDropout;
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


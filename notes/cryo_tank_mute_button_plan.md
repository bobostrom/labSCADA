# Cryo Storage Tank Physical Alarm Mute Pushbutton Plan

This engineering plan specifies the hardware, electrical wiring, CODESYS PLC ladder/structured text logic, and SCADA integration for adding dedicated physical alarm mute pushbuttons to the cryogenic liquid nitrogen storage dewars at **Advanced Fertility of Alaska**.

---

## 1. Operational Motivation & Clinical Ergonomics

### The Problem with Touchscreens & Mobile Devices in Cryo Storage
1. **Cryogenic Glove Incompatibility**: Staff wear bulky, heavily insulated cryogenic gloves rated for $-196^\circ\text{C}$ liquid nitrogen when pulling specimen canisters, canes, or performing dipstick frost line checks. Operating mobile phones or glass touchscreen kiosks with cryo gloves is cumbersome, slow, and breaches aseptic technique.
2. **Immediate Access at Point of Care**: When a dewar neck plug is lifted, ambient cleanroom air enters the neck, rapidly warming the vapor probe toward $-135^\circ\text{C}$ within 30 to 60 seconds. A physical button directly at the tank enables staff to slap the mute control with a gloved thumb or palm immediately before opening.
3. **Fail-Safe Specimen Protection**: If staff is urgently summoned to an operative procedure or emergency while specimens are out, the PLC automatically guarantees that alarms re-engage after 15 minutes. Patient specimens are never left permanently unmonitored.

---

## 2. Hardware Architecture & Electrical Specification

### WAGO I/O Component Allocation
From existing lab inventory (see [distributed_hardware_inventory_and_pod_wiring.md](file:///home/bobostrom/Projects/labSCADA/notes/distributed_hardware_inventory_and_pod_wiring.md)), two spare **WAGO 750-431** 8-channel 24V DC Digital Input slices are on the shelf.

```
                  ┌──────────────────────────────────────────────┐
                  │    CENTRAL WAGO PFC200 / PLC CONTROLLER      │
                  │    CODESYS V3.5 Runtime (OPC UA Server)      │
                  └───────────────────────┬──────────────────────┘
                                          │ Cat6 Ethernet
            ┌─────────────────────────────┴─────────────────────────────┐
            ▼                                                           ▼
 ┌─────────────────────────────┐                             ┌─────────────────────────────┐
 │ POD 3A: CRYO DEWAR 01 (EMBRYO)                            │ POD 3B: CRYO DEWAR 02 (SPERM)│
 │ • Coupler: WAGO 750-363     │                             │ • Coupler: WAGO 750-341     │
 │ • Slot 1:  750-461 (RTD)    │                             │ • Slot 1:  750-461 (RTD)    │
 │ • Slot 2:  750-431 (8x DI)  │ ◄── [Add Spare Slice]       │ • Slot 2:  750-431 (8x DI)  │ ◄── [Add Spare Slice]
 │ • Slot 3:  750-600 (Term)   │                             │ • Slot 3:  750-600 (Term)   │
 └──────────────┬──────────────┘                             └──────────────┬──────────────┘
                │ 24V DC DI Loop                                            │ 24V DC DI Loop
                ▼                                                           ▼
     [ Tank 1 Mute Button ]                                      [ Tank 2 Mute Button ]
```

### Pushbutton Hardware Requirements
- **Enclosure / Mount**: Stainless steel or chemically resistant sealed IP65/IP66 pod mounted directly on the dewar roller base or adjacent wall.
- **Actuator**: Industrial momentary palm button or flush 22mm / 30mm sealed push button (easy to hit with gloved palm, forearm, or elbow).
- **Illumination (Optional / Recommended)**: 24V DC LED ring indicator:
  - **OFF**: Standard live monitoring.
  - **SOLID ON**: Mute active (safe to remove neck plug).
  - **FAST FLASH (Last 2 minutes)**: Approaching auto-expiry warning to reseal lid.

---

## 3. CODESYS PLC Architecture (Single Point of Truth)

In strict accordance with the IVF SCADA architectural rule, the PLC is the deterministic point of truth for timing, alarm gating, and safety states.

### State Transition Diagram
```
                     ┌────────────────────────────────────────┐
                     │         MONITORING (NORMAL)            │
                     │    bCryoTank1Muted = FALSE             │
                     │    Alarms enabled on excursion         │
                     └───────────────────┬────────────────────┘
                                         │
                         [Button Pressed: R_TRIG]
                                         ▼
                     ┌────────────────────────────────────────┐
                     │          PAUSED / MUTED (15M)          │
                     │    bCryoTank1Muted = TRUE              │
                     │    Alarms suppressed; TON active       │
                     └─────────┬────────────────────┬─────────┘
                               │                    │
            [15m Expired: tonHold.Q]    [Button Pressed Again: R_TRIG]
                               │                    │
                               └─────────┬──────────┘
                                         ▼
                               (Return to NORMAL)
```

### PLC Implementation Code (`PLC_PRG.st`)

```pascal
VAR
    (* --- Physical Digital Inputs (WAGO 750-431) --- *)
    di_CryoTank1_MuteBtn    : BOOL;     (* Physical Pushbutton on Tank 1 *)
    di_CryoTank2_MuteBtn    : BOOL;     (* Physical Pushbutton on Tank 2 *)

    (* --- Edge Detectors --- *)
    rTrig_Cryo1Btn          : R_TRIG;
    rTrig_Cryo2Btn          : R_TRIG;

    (* --- SCADA Remote Override Bits (From Web/Mobile) --- *)
    bScada_Cryo1MuteCmd     : BOOL;     (* One-shot trigger from SCADA *)
    bScada_Cryo2MuteCmd     : BOOL;

    (* --- Mute Status Flags & Timers --- *)
    bCryoTank1Muted         : BOOL := FALSE;
    bCryoTank2Muted         : BOOL := FALSE;
    tonCryoTank1Hold        : TON;
    tonCryoTank2Hold        : TON;

    (* --- Remaining Time Output (for OPC UA / SCADA Telemetry) --- *)
    rCryoTank1RemainingSec  : REAL := 0.0;
    rCryoTank2RemainingSec  : REAL := 0.0;
END_VAR

// ==============================================================================
// CRYO TANK 1 ALARM MUTE LOGIC (15-MINUTE FAILSAFE)
// ==============================================================================
rTrig_Cryo1Btn(CLK := di_CryoTank1_MuteBtn OR bScada_Cryo1MuteCmd);
bScada_Cryo1MuteCmd := FALSE; // Auto-reset command pulse

// Toggle state on button press (push to mute, push again to cancel)
IF rTrig_Cryo1Btn.Q THEN
    bCryoTank1Muted := NOT bCryoTank1Muted;
END_IF;

// 15-Minute Failsafe Hold Timer
tonCryoTank1Hold(IN := bCryoTank1Muted, PT := T#15M);

// Automatically restore monitoring when time expires
IF tonCryoTank1Hold.Q THEN
    bCryoTank1Muted := FALSE;
END_IF;

// Calculate remaining countdown seconds for SCADA
IF bCryoTank1Muted THEN
    rCryoTank1RemainingSec := TIME_TO_REAL(T#15M - tonCryoTank1Hold.ET) / 1000.0;
ELSE
    rCryoTank1RemainingSec := 0.0;
END_IF;

// Output Alarm Evaluation Gated by Mute Flag
bCryoTank1Alarm := fbCryo1Alarm.bAlarm AND NOT bCryoTank1Muted;
bCryoTank1Warn  := fbCryo1Alarm.bPickup AND NOT fbCryo1Alarm.bAlarm AND NOT bCryoTank1Muted;


// ==============================================================================
// CRYO TANK 2 ALARM MUTE LOGIC (15-MINUTE FAILSAFE)
// ==============================================================================
rTrig_Cryo2Btn(CLK := di_CryoTank2_MuteBtn OR bScada_Cryo2MuteCmd);
bScada_Cryo2MuteCmd := FALSE;

IF rTrig_Cryo2Btn.Q THEN
    bCryoTank2Muted := NOT bCryoTank2Muted;
END_IF;

tonCryoTank2Hold(IN := bCryoTank2Muted, PT := T#15M);

IF tonCryoTank2Hold.Q THEN
    bCryoTank2Muted := FALSE;
END_IF;

IF bCryoTank2Muted THEN
    rCryoTank2RemainingSec := TIME_TO_REAL(T#15M - tonCryoTank2Hold.ET) / 1000.0;
ELSE
    rCryoTank2RemainingSec := 0.0;
END_IF;

bCryoTank2Alarm := fbCryo2Alarm.bAlarm AND NOT bCryoTank2Muted;
bCryoTank2Warn  := fbCryo2Alarm.bPickup AND NOT fbCryo2Alarm.bAlarm AND NOT bCryoTank2Muted;
```

---

## 4. OPC UA & SCADA Channel Mapping

The CODESYS Symbol Configuration publishes the following tags to Rapid SCADA:

| PLC Variable | Type | OPC UA Node | Rapid SCADA Channel | Description |
| :--- | :---: | :--- | :---: | :--- |
| `bCryoTank1Muted` | `BOOL` | `Application.PLC_PRG.bCryoTank1Muted` | **126** | Tank 1 Mute Active Flag |
| `bCryoTank2Muted` | `BOOL` | `Application.PLC_PRG.bCryoTank2Muted` | **127** | Tank 2 Mute Active Flag |
| `rCryoTank1RemainingSec` | `REAL` | `Application.PLC_PRG.rCryoTank1RemainingSec` | **128** | Tank 1 Hold Remaining Seconds |
| `rCryoTank2RemainingSec` | `REAL` | `Application.PLC_PRG.rCryoTank2RemainingSec` | **129** | Tank 2 Hold Remaining Seconds |
| `bScada_Cryo1MuteCmd` | `BOOL` | `Application.PLC_PRG.bScada_Cryo1MuteCmd` | Command | SCADA Web Remote Trigger |
| `bScada_Cryo2MuteCmd` | `BOOL` | `Application.PLC_PRG.bScada_Cryo2MuteCmd` | Command | SCADA Web Remote Trigger |

---

## 5. SCADA Alert Engine & Web UI Behavior

1. **Dual Synchronized Triggering**:
   - Tapping the physical button on Tank 1 immediately sets Channel 126 (`bCryoTank1Muted = 1`).
   - The Wall Kiosk dashboard, Mobile `/log` page, and PostgreSQL audit tables update simultaneously.
2. **Pushover Siren Silence**:
   - While `bCryoTank1Muted = TRUE`, the alert engine suppresses Priority 2 emergency sirens and Pushover notifications for vapor probe fluctuations.
3. **Audit Trail Logging**:
   - Each transition (Button Pressed $\rightarrow$ Hold Started; Button Pressed Again $\rightarrow$ Hold Canceled; or 15m Expired) is automatically logged to `mod_arc_postgre_sql.cryo_maintenance_holds` with initiator `"Physical Tank Button"`.
4. **Visual Indicator on Tank Card**:
   - The Kiosk card top border glows amber (`#f59e0b`).
   - The badge updates to `HOLD (14m remaining)`.
   - The sub-button displays `🟡 Muted • Tap to Resume`.

---

## 6. Implementation Rollout Checklist

- [ ] **Physical Hardware**:
  - Mount cleanroom-sealed momentary pushbutton on Cryo Tank 1 and Tank 2 pods.
  - Wire 24V DC wetting loop to Digital Input slice (WAGO 750-431).
- [ ] **CODESYS Project**:
  - Insert DI slice into Pod 3A and Pod 3B I/O configuration.
  - Add `bCryoTank1Muted`, `tonCryoTank1Hold`, and logic into `PLC_PRG.st`.
  - Add tags to `SCADAdemo.Device.Application.xml` Symbol Configuration.
- [ ] **Rapid SCADA**:
  - Add Channels 126–129 to `DrvOpcUa_001.xml` and `/opt/scada/ScadaComm/Config/`.
  - Restart `scadacomm6`.
- [ ] **Alert Engine & Dashboard**:
  - Bind Channel 126/127 mute states to `ivf_alert_engine.py` and Kiosk telemetry updates.

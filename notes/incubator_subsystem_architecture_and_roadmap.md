# IVF Incubator Subsystem Architecture & Integration Roadmap

## 1. Executive Summary & Hardware Hierarchy

The physical setup in the embryology lab separates the **climate-controlled furniture enclosure** from the **incubation instruments** themselves:

```
[ Incubator Cabinet 01 (Enclosure) ]
  ├── Cabinet Door Switch (DI 8 / Bit 7) - Slide-out access monitoring
  ├── Slide-out Trays (Capacity: 3 Bays)
  │     ├── Tray 1: K-Systems G210 #1 (Chamber Alarm Dry Contact DI 1 -> Ch 123)
  │     ├── Tray 2: K-Systems G210 #2 (Chamber Alarm Dry Contact DI 2 -> Ch 124)
  │     └── Tray 3: [ Empty / Unpopulated Expansion Bay ]
  ├── Cabinet Interior Temperature Sensor (RTD) - Measures trapped waste heat (Future)
  └── Cabinet Exhaust Fan Relay (DO) - Autonomous thermostatic cooling by WAGO 750-8212 (Future)

[ Standalone Box Incubators ]
  └── Astec SCA-165DRS #1 (Chamber Alarm Dry Contact + External RTD Probe)
```

> [!IMPORTANT]
> ### WAGO 750-8212 Controller: Single Point of Truth
> All fieldbus polling, timers, and alarm gating **MUST** route strictly through the **WAGO PFC200 (750-8212)** PLC (`afoa-plc.labmon`):
> 1. Remote Coupler (`afoa-node00.labmon`, WAGO 750-352) operates purely as a remote I/O slice, polled over Modbus TCP by the 750-8212.
> 2. The 750-8212 executes `FB_IncubatorCabinet` deterministically in `PLC_PRG.st`.
> 3. Nuisance alarms are suppressed directly inside the PLC logic: `bRawContact := (bIncubator01_RawContact AND NOT fbCabinet01.bIncubatorMute)`.
> 4. ScadaComm subscribes to the 750-8212 OPC UA Server (`:4840`) and writes directly into PostgreSQL (`mod_arc_postgre_sql.curcopy_current`).
> 5. The Alert Engine and Wall Kiosk read from PostgreSQL—**never polling remote field couplers directly**.

---

## 2. Channel & OPC UA Tag Mapping

| Variable / Function | OPC UA Node ID (`ns=4;s=...`) | ScadaComm TagCode | Rapid SCADA Channel | Function |
| :--- | :--- | :--- | :---: | :--- |
| `fbCabinet01.bDoorOpen` | `...Application.PLC_PRG.fbCabinet01.bDoorOpen` | `Temperature_08` | **108** | Cabinet door open status (0 = Closed, 1 = Open) |
| `fbCabinet01.bIncubatorMute` | `...Application.PLC_PRG.fbCabinet01.bIncubatorMute` | `Temperature_09` | **109** | Incubator mute active (0 = Inactive, 1 = Muted) |
| `fbCabinet01.bDoorAlarm` | `...Application.PLC_PRG.fbCabinet01.bDoorAlarm` | `Temperature_10` | **110** | Door held open alarm (0 = Normal, 1 = Alarm > 3m) |
| `fbIncubator1.bAlarm` | `...Application.PLC_PRG.fbIncubator1.bAlarm` | `IncubatorAlarm_01` | **123** | G210 #1 Debounced Chamber Alarm |
| `fbIncubator2.bAlarm` | `...Application.PLC_PRG.fbIncubator2.bAlarm` | `IncubatorAlarm_02` | **124** | G210 #2 Debounced Chamber Alarm |

---

## 3. CODESYS Implementation (`PLC_PRG.st`)

```pascal
(* --- Incubator Cabinet Enclosure Execution --- *)
fbCabinet01(
    bDoorRawContact     := bCabinetDoor_RawContact,
    tDoorAlarmDelay     := T#3M,
    tPostCloseGrace     := T#3M,
    bSimMode            := FALSE,
    rCabinetTemp        := 24.5,
    rFanOnSetpoint      := 28.0,
    rFanHysteresis      := 1.5
);

(* --- Incubator Function Block Execution (Gated by Cabinet Mute) --- *)
fbIncubator1(
    bRawContact := (bIncubator01_RawContact AND NOT fbCabinet01.bIncubatorMute),
    tDebounce   := T#15S
);

fbIncubator2(
    bRawContact := (bIncubator02_RawContact AND NOT fbCabinet01.bIncubatorMute),
    tDebounce   := T#15S
);
```

# WAGO Distributed I/O Pod Wiring & Hardware Inventory

This engineering note specifies the exact physical wiring, module assignments, network topology, and channel allocations for the distributed cleanroom monitoring stations at **Advanced Fertility of Alaska**.

---

## 1. System Architecture Overview

The system uses a distributed edge pod architecture connected to a central automation controller (WAGO PFC200 / Scada Host):

```
                       ┌────────────────────────────────────────┐
                       │   CENTRAL CONTROLLER / SCADA HOST      │
                       │   WAGO PFC200 (750-8212) / Edge PC     │
                       │   CODESYS V3.5 • Web Kiosk • Alerts    │
                       └───────────────────┬────────────────────┘
                                           │ Main Industrial Network (Cat6)
         ┌─────────────────────────────────┼────────────────────────────────┐
         │ (Cleanroom Suite Line)          │ (Dedicated Cryo Line A)        │ (Dedicated Cryo Line B)
         ▼                                 ▼                                ▼
┌──────────────────┐             ┌──────────────────┐             ┌──────────────────┐
│ POD 1: INCUBATORS│             │ POD 3A: DEWAR 01 │             │ POD 3B: DEWAR 02 │
│ WAGO 750-363 (P1)│             │ WAGO 750-363     │             │ WAGO 750-341     │
│ 750-431 DI Slice │             │ 750-461 RTD Slice│             │ 750-461 RTD Slice│
│ 750-600 End Term │             │ 750-600 End Term │             │ 750-600 End Term │
└────────┬─────────┘             └──────────────────┘             └──────────────────┘
         │ Daisy-Chain Cat6       (Mounted on Dewar 1)             (Mounted on Dewar 2)
         ▼
┌──────────────────┐
│ POD 2: MED COLD  │
│ WAGO 750-363 (P1)│
│ 750-461 RTD Slice│
│ 750-431 DI Slice │
│ 750-600 End Term │
└──────────────────┘
 (Medication Room)
```

---

## 2. Hardware Inventory & Station Allocation

All distributed edge pods are populated from the WAGO 750 component inventory:

| Module Part # | Description | Total in Stock | Allocated Pod(s) | Spares on Shelf |
| :--- | :--- | :---: | :--- | :---: |
| **`750-341`** | Ethernet TCP/IP Coupler (1x RJ-45, Modbus TCP) | 1 | **Pod 3B** *(Cryo Dewar 02)* | 0 |
| **`750-363`** | EtherNet/IP 2-Port Coupler (Integrated Switch) | 3 | **Pod 1** *(Incubators)*, **Pod 2** *(Fridge/Freezer)*, **Pod 3A** *(Cryo Dewar 01)* | 0 |
| **`750-461`** | 2-Channel Pt100/Pt1000 RTD Input ($-200^\circ\text{C}$ to $+850^\circ\text{C}$) | 3 | **Pod 2** (1), **Pod 3A** (1), **Pod 3B** (1) | 0 *(Optional 3x in reserve)* |
| **`750-431`** | 8-Channel 24V DC Digital Input (High-Side) | 4 | **Pod 1** (1x Incubators), **Pod 2** (1x Doors) | **2 Spares** |
| **`750-530`** | 8-Channel 24V DC Digital Output (0.5A) | 4 | **Pod 1** (1x Local visual strobe/alarm light) | **3 Spares** |
| **`750-600`** | Bus End Module (K-Bus Terminator) | 4 | **Pod 1** (1), **Pod 2** (1), **Pod 3A** (1), **Pod 3B** (1) | **0** *(Exact match)* |
| **`750-602` / `601`**| 24V DC Field Power Supply Feeder Slices | 3 | Available for field-side potential distribution | **3 Spares** |
| **`750-614`** | 0V Potential Distribution Module | 1 | Common ground reference jumper | **1 Spare** |
| **`750-478`** | 2-Channel 0–10V DC Analog Input Module | 2 | Cleanroom pressure or O2 monitoring | **2 Spares** |
| **`750-415`** | 4-Channel 24V AC/DC Digital Input Module | 2 | Isolated building management inputs | **2 Spares** |
| **`750-436`** | 8-Channel 24V DC Digital Input Module (Sink) | 1 | NPN proximity or sensor inputs | **1 Spare** |

---

## 3. Pod Specifications & Channel Mappings

### Pod 1: Cleanroom Incubator Suite
* **Location:** Polycarbonate wall enclosure (~8"×8"×4") adjacent to Incubators 01 & 02.
* **Network Connection:** 
  - **Port 1 (In):** Cat6 drop from central network switch.
  - **Port 2 (Out):** Daisy-chain Cat6 line to Pod 2 (Medication Room).
* **Protocol:** EtherNet/IP (or Modbus TCP).
* **Power:** 24V DC via PoE Splitter or local DIN power supply.
* **Hardware Stack:**
  1. `750-363` — Fieldbus Coupler (2-Port)
  2. `750-431` — 8-Channel 24V DC Digital Input
  3. `750-530` — 8-Channel 24V DC Digital Output (Optional strobe/buzzer)
  4. `750-600` — Bus End Module

#### Pinout & Channel Assignments:
| Terminal | Signal | Connected Device | Function | SCADA Channel |
| :---: | :--- | :--- | :--- | :---: |
| **DI 1** | 24V Input | Incubator 01 Alarm Relay (Dry Contact) | NC loop opens on chamber alarm | **Ch 123** |
| **DI 2** | 24V Input | Incubator 02 Alarm Relay (Dry Contact) | NC loop opens on chamber alarm | **Ch 124** |
| **DI 3** | 24V Input | Incubator Suite Gas Pressure Switch | Low N2/CO2 supply pressure warning | *Ch 127 (Spare)* |
| **DI 4–8**| 24V Input | Spare Field Inputs | Expansion | *Spares* |
| **DO 1** | 24V Output | Cleanroom Local Visual Strobe Light | Pulsed on active Priority 2 alarm | *Relay 1* |

---

### Pod 2: Medical Cold Storage (Medication Prep Room)
* **Location:** Wall-mounted enclosure between the medication refrigerator and freezer.
* **Network Connection:** 
  - **Port 1 (In):** Daisy-chained Cat6 run from Pod 1 (Port 2).
* **Protocol:** EtherNet/IP.
* **Power:** 24V DC via local DIN supply or PoE Splitter.
* **Hardware Stack:**
  1. `750-363` — Fieldbus Coupler (2-Port)
  2. `750-461` — 2-Channel Pt100 RTD Input ($-200^\circ\text{C}$ to $+850^\circ\text{C}$)
  3. `750-431` — 8-Channel 24V DC Digital Input
  4. `750-600` — Bus End Module

#### Pinout & Channel Assignments:
| Terminal | Signal | Connected Device | Function | Calibration Limits | SCADA Channel |
| :---: | :--- | :--- | :--- | :---: | :---: |
| **AI 1** | Pt100 (2/3-wire) | Medical Refrigerator Probe | Glycol-buffered probe inside fridge | Target: $2.0^\circ\text{C} - 8.0^\circ\text{C}$ | **Ch 102** |
| **AI 2** | Pt100 (2/3-wire) | Medical Freezer Probe | Air/glycol probe inside freezer | Limit: $< -15.0^\circ\text{C}$ | **Ch 103** |
| **DI 1** | 24V Input | Fridge Door Magnetic Reed Switch | Closed when door shut | Holdoff timer (Ch 111) | **Ch 115** |
| **DI 2** | 24V Input | Freezer Door Magnetic Reed Switch | Closed when door shut | Holdoff timer (Ch 112) | **Ch 116** |

---

### Pod 3A: Cryo Dewar 01 — Embryos (On-Tank Mobile Pod)
* **Location:** Compact industrial NEMA box (8"×6"×4") bolted directly to the **Dewar 01 roller cart/body**.
* **Mobility Design:** 
  - The Pt100 RTD sensor wire runs only 12 inches from the dewar neck into the box. **It is strain-relieved and never flexes or moves.**
  - A single heavy-duty, snagless Cat6 patch cable (with a 20-foot service loop) runs from the wall to the dewar box.
* **Power & Data:** Standard Cat6 PoE from the cryo room switch into an internal **PoE Splitter** (e.g. Planet `IPOE-162S` or TP-Link `TL-POE10R`) providing 24V DC to the coupler.
* **Hardware Stack:**
  1. `750-363` — Fieldbus Coupler (2-Port)
  2. `750-461` — 2-Channel Pt100 RTD Input
  3. `750-600` — Bus End Module

#### Pinout & Channel Assignments:
| Terminal | Signal | Connected Device | Function | Alarm Threshold | SCADA Channel |
| :---: | :--- | :--- | :--- | :---: | :---: |
| **AI 1** | Pt100 (3-wire) | Dewar 01 Vapor Phase Probe | Upper neck canister level monitoring | Warning: $> -140^\circ\text{C}$<br>Alarm: $> -135^\circ\text{C}$ | **Ch 125** |
| **AI 2** | Pt100 (3-wire) | Dewar 01 Reserve / Liquid Level | Secondary bottom/liquid verification | Level delta verification | *Ch 126 (Spare)* |

---

### Pod 3B: Cryo Dewar 02 — Sperm (On-Tank Mobile Pod)
* **Location:** Compact industrial NEMA box (8"×6"×4") bolted directly to the **Dewar 02 roller cart/body**.
* **Mobility Design:** Identical on-tank protected wiring; single Cat6 PoE connection.
* **Network Connection:** Dedicated Cat6 home-run cable from the cryo room switch plate.
* **Protocol:** Modbus TCP (native).
* **Hardware Stack:**
  1. `750-341` — Fieldbus Coupler (1-Port, Modbus TCP)
  2. `750-461` — 2-Channel Pt100 RTD Input
  3. `750-600` — Bus End Module

#### Pinout & Channel Assignments:
| Terminal | Signal | Connected Device | Function | Alarm Threshold | SCADA Channel |
| :---: | :--- | :--- | :--- | :---: | :---: |
| **AI 1** | Pt100 (3-wire) | Dewar 02 Vapor Phase Probe | Upper neck canister level monitoring | Warning: $> -140^\circ\text{C}$<br>Alarm: $> -135^\circ\text{C}$ | **Ch 104** |
| **AI 2** | Pt100 (3-wire) | Dewar 02 Reserve Probe | Spare | - | *Spare* |

---

## 4. Cryo Dewar Cabling Strategy: Why On-Tank Beats Wall Boxes

```
[ DEWAR BODY ]
  │
  ├─► [ Tank Neck ] ──(12-inch rigid Pt100 lead)──► [ On-Tank Junction Box ]
  │                                                  │ • WAGO 750 Coupler
  │                                                  │ • WAGO 750-461 RTD Slice
  │                                                  │ • 24V PoE Splitter
  │                                                  └─────────▲─────────
  │                                                            │
  └─► [ Heavy-Duty Casters ]                                   │ (Rugged, flexible Cat6 Cable
                                                               │  with 20-ft service loop)
                                                               │
                                                       [ Cryo Room Wall Plate ]
```

### The Reliability Advantages:
1. **Zero Stress on RTD Leads:** Thin cryogenic sensor leads (24–26 AWG) are never dragged across the floor or pinched under caster wheels.
2. **Field-Serviceable Cat6:** If an Ethernet patch cable is ever pinched or severed by a rolling dewar, an off-the-shelf $5 Cat6 cable can be swapped in 10 seconds without affecting probe calibration.
3. **No 120V Near Liquid Nitrogen:** Delivering 24V DC power over the Cat6 cable via PoE splitters eliminates high-voltage extension cords near cryogenic vessels.
4. **Star Topology Autonomy:** Because Dewar 01 and Dewar 02 connect over separate Cat6 runs, either tank can be temporarily unplugged, moved to the filling dock, or wheeled to surgery without interrupting readings on the other tank.

---

## 5. CODESYS & Rapid SCADA Integration

### Coupler Addressing & Protocols:
* **`Pod 1` (Incubators):** `192.168.10.141` — Protocol: EtherNet/IP (WAGO 750-363 EDS).
* **`Pod 2` (Med Cold):** `192.168.10.142` — Protocol: EtherNet/IP (WAGO 750-363 EDS).
* **`Pod 3A` (Dewar 01):** `192.168.10.143` — Protocol: EtherNet/IP (WAGO 750-363 EDS).
* **`Pod 3B` (Dewar 02):** `192.168.10.144` — Protocol: Modbus TCP (Unit ID 1, Port 502).

### Pt100 Data Scaling in PLC:
The `750-461` module returns integer values representing temperature in tenths of a degree Celsius ($0.1^\circ\text{C}$):
$$\text{Temperature }(^\circ\text{C}) = \frac{\text{Raw Integer Value}}{10.0}$$
* *Example:* Raw value `85` = $8.5^\circ\text{C}$ (Fridge Excursion).
* *Example:* Raw value `-1423` = $-142.3^\circ\text{C}$ (Cryo Normal).
* *Sensor Error Codes:* Values $\ge 32760$ denote open circuit / disconnected probe.

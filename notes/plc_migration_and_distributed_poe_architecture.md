# IVF Lab SCADA: PLC Evaluation, Distributed Pods & PoE Architecture

## 1. Executive Summary

This document captures the design exploration and feasibility analysis for modernizing and distributing the laboratory telemetry system currently managed by the **SEL RTAC** at *Advanced Fertility of Alaska*.

It documents:
1. **Controller Evaluation:** An engineering comparison between the SEL RTAC, Raspberry Pi / OpenPLC, and modern industrial PLCs (WAGO).
2. **Distributed Pod Topology:** A solution to the physical challenge of widely dispersed cleanroom equipment (Incubators, Med Refrigerators/Freezers, and Cryogenic LN2 Storage).
3. **Power over Ethernet (PoE) Integration:** Using industrial DIN-rail PoE splitters (Planet `IPOE-162S`) to power remote pods over single Cat6 drops with centralized UPS backup.
4. **Complete Bill of Materials (BOM):** Itemized hardware lists, part numbers, and wiring guidelines.

---

## 2. Controller Architecture Brainstorming

### A. The Baseline: SEL RTAC (Current Implementation)
* **Profile:** Substation-grade utility controller (e.g., SEL-3530 / SEL-3555 / SEL-2411).
* **Strengths:** 
  * Unrivaled MTBF (>300 years) and 10-year no-questions-asked warranty.
  * Extreme surge, ESD, and electrical noise immunity designed for high-voltage power substations.
  * Hard deterministic real-time OS (RTOS) that virtually never crashes.
* **Limitations:**
  * AcSELerator RTAC engineering software is rigid and power-grid centric.
  * High expansion cost per I/O point.
  * Lacks native modern web/IoT protocols (e.g., MQTT, REST/JSON, OPC UA) without custom conversion logic.

### B. Raspberry Pi + OpenPLC: Why It Is Not Defensible in an IVF Lab
* **The Appeal:** Inexpensive hardware, full Linux access, and open-source ladder logic.
* **The Failure Points in Clinical Embryology:**
  * **Storage Exhaustion:** Consumer MicroSD cards suffer rapid write fatigue and silent filesystem corruption under continuous 24/7 logging.
  * **Lack of Isolation:** Standard Pi GPIOs lack optoisolation, industrial surge/ESD suppression, and reverse-polarity protection. Compressor cycles or solenoid kicks can freeze the bus.
  * **Regulatory & Malpractice Liability:** If human gametes or embryos are lost because a DIY Raspberry Pi or OpenPLC runtime hung, the absence of certified industrial hardware creates catastrophic liability during CAP/CLIA inspections and legal discovery.

### C. Modern Modular PLC: WAGO PFC200 (Selected Alternative)
* **The Sweet Spot:** 
  * Industrial reliability, UL/CE certifications, and vibration-proof CAGE CLAMP spring terminals.
  * Native snap-on slice I/O for direct RTDs (Pt100/Pt1000) and cryogenic thermocouples (down to -200°C) with no external signal conditioning transmitters.
  * Linux real-time PREEMPT OS running CODESYS V3.
  * Dual independent Ethernet interfaces (air-gaps cleanroom OT sensors from clinic LAN).
  * Native MQTT, OPC UA, Modbus TCP, and HTML5 WebVisu onboard.

---

## 3. Physical Layout Challenge: Distributed "Satellite Pods"

### The Problem
* The **Medication Fridge and Freezer** are located in the preparation/med area.
* The **Liquid Nitrogen (LN2) Cryo Tanks** are located in the cryogenic storage dewar room.
* The **Incubators** are inside the cleanroom suite.
* The **Main SCADA / Server Cabinet** is located in an electrical/utility room.

Running raw analog sensor wiring (microvolt thermocouple wires and resistance-sensitive RTD cables) across rooms introduces severe noise from compressor motors, lead-resistance error, and difficult cleanroom wall penetrations.

### The Solution: "Digitize at the Source"
Deploy **3 Remote Satellite Pods** connected via standard Cat6 Ethernet back to the central controller cabinet. Each pod houses a WAGO Modbus TCP coupler and local slice I/O inside a cleanroom-washable NEMA 4X / IP66 enclosure.

```
 [ CLEANROOM / LAB OT NETWORK (192.168.10.x) ]
   │
   ├──► POD 1: Incubator Pod (Modbus TCP)
   │     • Incubator Alarm Dry Contacts (Incubator 01, 02)
   │     • Incubator Cabinet Door Magnetic Switch
   │
   ├──► POD 2: Med Fridge & Freezer Pod (Modbus TCP)
   │     • Med Fridge RTD (-2°C to 10°C) [Cnl 102]
   │     • Med Freezer RTD (-30°C to 0°C) [Cnl 103]
   │     • Fridge & Freezer Door Reed Switches
   │
   ├──► POD 3: Cryo Storage Tank Pod (Modbus TCP)
   │     • Cryo Tank 1 Probe (-200°C to -100°C) [Cnl 125]
   │     • Spare channel for Tank 2 / LN2 level
   │
   ▼
[ CENTRAL CONTROLLER CABINET (WAGO PFC200) ]
   • Onboard I/O: Facility Perimeter Doors (Main Entry, Cryo Room Door)
   • Coordination Logic: Recovery Holdoff Timers, Siren Strobes, Kiosk Silence Logic
   • Port 1 (OT): Continuous Modbus TCP polling of Pods 1, 2, 3
   • Port 2 (IT): Connected to Clinic LAN ──► Rapid SCADA / PostgreSQL / Grafana
```

---

## 4. Power over Ethernet (PoE) Strategy

### Why PoE is the Best Practice for Cleanrooms
1. **Single-Cable Deployment:** A single Cat6 cable provides both high-speed Modbus TCP communication and 24V DC operating power. No 120V AC electrical drops or conduit permits required inside sterile or cryogenic zones.
2. **Centralized UPS & Generator Redundancy:** By powering the pods from a central IT PoE switch backed by a central UPS battery bank and building emergency generator, all remote pods remain 100% operational during mains power blackouts.
3. **Remote Reboot Capability:** If a pod ever needs a power cycle, staff can power-cycle the switch port remotely from the network management console without entering the cleanroom.

### Power Budget Feasibility
* **WAGO `750-362` Coupler:** ~2.5 W – 3.0 W
* **WAGO `750-464` (RTD Slice):** ~0.3 W
* **WAGO `750-469` (Thermocouple Slice):** ~0.3 W
* **WAGO `750-1405` (Digital Inputs):** ~0.5 W – 1.0 W (all active)
* **Total Peak Pod Consumption:** **~4.0 W to 5.0 W**
* *Standard PoE (IEEE 802.3af Type 1)* supplies up to **12.95 W** at the device, providing **>2.5× safety margin** on basic PoE switch ports.

### Hardware Interface: Planet `IPOE-162S`
The WAGO `750-362` coupler accepts 24V DC on terminal blocks. Inside each pod, a **Planet `IPOE-162S` Industrial DIN-rail PoE+ Splitter** splits incoming Cat6 PoE into:
1. **RJ45 Data Patch:** Connects into the WAGO coupler Ethernet port.
2. **24V DC Screw Terminals:** Jumpers into the WAGO coupler power bus.

---

## 5. Complete Bill of Materials (BOM)

### Pod 1: Incubator Monitoring Pod (Cleanroom Suite)
*Monitors incubator alarm dry contacts (Incubator 01, 02) and incubator cabinet access door switches.*

| Item | Manufacturer | Part Number | Description | Qty | Purpose |
| :--- | :--- | :--- | :--- | :---: | :--- |
| 1.1 | Planet | `IPOE-162S` | Industrial PoE+ Splitter (12V/24V DC out, DIN rail) | 1 | PoE to 24V DC terminal power |
| 1.2 | WAGO | `750-362` | Modbus TCP Fieldbus Coupler | 1 | Pod network head |
| 1.3 | WAGO | `750-1405` | 16-Channel 24V DC Digital Input Slice | 1 | Incubator alarm contacts & door switches |
| 1.4 | WAGO | `750-600` | End Module | 1 | WAGO 750 bus terminator |
| 1.5 | Fibox / Bud | NEMA 4X / IP66 | Polycarbonate Enclosure (~8" × 8" × 4") with DIN Rail | 1 | Cleanroom wall-mount pod box |
| 1.6 | Generic | Cat6 Patch | Slim 1 ft Shielded Cat6 Patch Cable | 1 | Data link: Splitter to Coupler |

---

### Pod 2: Med Cold Storage Pod (Medication Prep Room)
*Monitors medication refrigerator (Ch 102: 0°C to 10°C) and freezer (Ch 103: -30°C to 0°C).*

| Item | Manufacturer | Part Number | Description | Qty | Purpose |
| :--- | :--- | :--- | :--- | :---: | :--- |
| 2.1 | Planet | `IPOE-162S` | Industrial PoE+ Splitter (12V/24V DC out, DIN rail) | 1 | PoE to 24V DC terminal power |
| 2.2 | WAGO | `750-362` | Modbus TCP Fieldbus Coupler | 1 | Pod network head |
| 2.3 | WAGO | `750-464` | 4-Channel RTD Input Slice (Pt100/Pt1000, 2/3/4-wire) | 1 | Med Fridge (102), Med Freezer (103), + 2 spares |
| 2.4 | WAGO | `750-430` | 8-Channel 24V DC Digital Input Slice | 1 | Fridge/freezer door magnetic switches |
| 2.5 | WAGO | `750-600` | End Module | 1 | WAGO 750 bus terminator |
| 2.6 | Omega / TE | Pt100 3-Wire | Class A RTD Temp Probes w/ 10 ft PFA leads | 2 | Glycol-buffered probes in fridge & freezer |
| 2.7 | Fibox / Bud | NEMA 4X / IP66 | Polycarbonate Enclosure (~8" × 8" × 4") with DIN Rail | 1 | Wall-mount pod box |
| 2.8 | Generic | Cat6 Patch | Slim 1 ft Shielded Cat6 Patch Cable | 1 | Data link: Splitter to Coupler |

---

### Pod 3: Cryo Storage Tank Pod (Dewar Storage Room)
*Monitors cryogenic liquid nitrogen dewars down to -200°C (Ch 125).*

| Item | Manufacturer | Part Number | Description | Qty | Purpose |
| :--- | :--- | :--- | :--- | :---: | :--- |
| 3.1 | Planet | `IPOE-162S` | Industrial PoE+ Splitter (12V/24V DC out, DIN rail) | 1 | PoE to 24V DC terminal power |
| 3.2 | WAGO | `750-362` | Modbus TCP Fieldbus Coupler | 1 | Pod network head |
| 3.3 | WAGO | `750-469` | 2-Channel Thermocouple Slice (Type T / K) | 1 | Cryo Tank 1 (Ch 125 down to -200°C) + Tank 2 spare |
| 3.4 | WAGO | `750-600` | End Module | 1 | WAGO 750 bus terminator |
| 3.5 | Omega | Type T Cryo | Special Limits Type-T Thermocouple Probe | 1 | Probe rated for -200°C LN2 vapor/liquid phase |
| 3.6 | Fibox / Bud | NEMA 4X / IP66 | Polycarbonate Enclosure (~8" × 8" × 4") with DIN Rail | 1 | Wall-mount pod box near dewar bank |
| 3.7 | Generic | Cat6 Patch | Slim 1 ft Shielded Cat6 Patch Cable | 1 | Data link: Splitter to Coupler |

---

### Central Controller Cabinet (Main Plant / IT Location)
*Central automation hub, facility perimeter door monitoring, siren relays, and bridge to Grafana.*

| Item | Manufacturer | Part Number | Description | Qty | Purpose |
| :--- | :--- | :--- | :--- | :---: | :--- |
| 4.1 | WAGO | `750-8212` | PFC200 G2 Controller (2x ETH, RS-232/485, Linux) | 1 | Main coordinator; polls pods, evaluates holdoffs |
| 4.2 | WAGO | `787-1702` | Compact 24V DC Power Supply (1.25 A, 30 W, DIN rail) | 1 | Powers controller and local door inputs |
| 4.3 | WAGO | `750-1405` | 16-Channel 24V DC Digital Input Slice | 1 | Main Entry Door 01 (121), Cryo Door 02 (122), spares |
| 4.4 | WAGO | `750-512` | 2-Channel Relay Output Slice (230V AC / 30V DC, 5A) | 1 | Dry contact outputs to trigger cleanroom strobes |
| 4.5 | WAGO | `750-600` | End Module | 1 | WAGO 750 bus terminator |
| 4.6 | Saginaw | NEMA 12/4 | Wall-Mount Enclosure (~14" × 12" × 6") | 1 | Houses central controller and PSU |

---

### Network & Installation Accessories

| Item | Manufacturer | Part Number | Description | Qty | Purpose |
| :--- | :--- | :--- | :--- | :---: | :--- |
| 5.1 | Planet *(Optional)*| `IGS-504HPT` | 5-Port Industrial Gigabit PoE+ Switch (4x PoE+, 1x Uplink) | 1 | Dedicated industrial switch to power the 3 pods |
| 5.2 | Sealcon | `NPT 1/2"` | IP68 Liquid-Tight Nylon Cable Glands | 12 | Clean sealed wire entry into the 3 pod enclosures |
| 5.3 | WAGO | `2002-1201` | TOPJOB S 2-Conductor Terminal Blocks | 10 | 24V DC power distribution jumpers |

---

### Consolidated Total Hardware Roll-Up

| Item Category | Part Number | Total Qty |
| :--- | :--- | :---: |
| **PoE+ Splitter** | Planet `IPOE-162S` | **3** |
| **Modbus TCP Coupler** | WAGO `750-362` | **3** |
| **Main Controller** | WAGO `750-8212` (PFC200) | **1** |
| **24V DC Power Supply** | WAGO `787-1702` | **1** |
| **Bus End Modules** | WAGO `750-600` | **4** |
| **16-ch Digital Inputs** | WAGO `750-1405` | **2** |
| **8-ch Digital Inputs** | WAGO `750-430` | **1** |
| **4-ch RTD Temp Slice** | WAGO `750-464` | **1** |
| **2-ch Thermocouple Slice** | WAGO `750-469` | **1** |
| **2-ch Relay Outputs** | WAGO `750-512` | **1** |
| **Pod Enclosures (8×8×4")** | NEMA 4X Polycarbonate | **3** |

---

## 6. Wiring & Commissioning Guidelines

```
   Incoming Cat6 (from PoE Switch)
                 │
                 ▼
      ┌─────────────────────┐
      │  Planet IPOE-162S   │◄─── [DIP Switch set to 24V]
      └──────────┬──────────┘
      Data Out   │   24V DC Out
     (RJ45 Port) │   (Screw Terminals)
         │       │        │
         │  ┌────┴────────┼───────────────────┐
         │  │             │                   │
         ▼  ▼             ▼                   ▼
      ┌──────────┐  ┌──────────┐         ┌──────────┐
      │ RJ45 In  │  │ Sys 24V  │         │Field 24V │
      │          │  │  & 0V    │         │  & 0V    │
      │  WAGO    └──┴──────────┴─────────┴──────────┤
      │  750-362 Coupler Head                       │
      └─────────────────────────────────────────────┘
```

1. **Planet `IPOE-162S` DIP Switch:** Ensure the voltage slide switch is set to **`24V`** *before* connecting the PoE Ethernet cable.
2. **Coupler Dual-Feed Wiring:** The WAGO `750-362` coupler features two separate 24V power circuits:
   * **System Power (`24V/0V`):** Powers the internal coupler logic and slice communications bus.
   * **Field Power (`24V/0V`):** Powers the digital and analog field contacts.
   * *Wiring instruction:* Run an 18 AWG 2-wire jumper from the `IPOE-162S` 24V output to the System Power terminals, then daisy-chain to the Field Power terminals.
3. **Data Patch:** Connect the 1 ft shielded Cat6 patch cable from the `Data Out` RJ45 jack of the `IPOE-162S` into Port 1 of the WAGO `750-362`.
4. **Network Subnetting:**
   * Configure the 3 pods with static IP addresses on the isolated OT subnet (e.g., `192.168.10.11` for Incubators, `192.168.10.12` for Meds, `192.168.10.13` for Cryo).
   * Configure Port 1 of the WAGO PFC200 as `192.168.10.1` to poll all three pods seamlessly via Modbus TCP.

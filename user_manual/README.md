# IVF Laboratory SCADA: Cleanroom User Manual

Welcome to the **IVF Cleanroom SCADA & Environmental Monitoring System User Manual**. This manual serves as the operational guide for laboratory directors, clinical embryologists, technicians, and regulatory compliance inspectors at *Advanced Fertility of Alaska*.

---

## Quick System Access

* **Cleanroom Touchscreen Kiosk:** `http://192.168.10.133/` (Standard Port 80)
* **Cryo Tank Audit Suite:** `http://192.168.10.133/cryo`
* **Monthly Compliance Report Packet (3 Pages):** `http://192.168.10.133/report/ln2` (Interactive month picker & print styling)
* **Printable Station QR Placard (For External Cryo Tanks):** `http://192.168.10.133/print/qr`
* **Mobile LN2 Dipstick Entry (Smartphone QR Destination):** `http://192.168.10.133/log` (select Tank 1 or Tank 2 on form)
* **Daily CAP Verification:** Accessible directly via the top banner on the Live Operations view.
* **Individual Tank Reports:**
  * Cryo Tank 1 (Embryos): `http://192.168.10.133/report/ln2/html?tank=1`
  * Cryo Tank 2 (Sperm Incident): `http://192.168.10.133/report/ln2/html?tank=2`
* **Rapid SCADA Administrator Portal:** `http://192.168.10.133:10008/` (or `/scada/`)

---

## User Manual Sections

```
user_manual/
├── README.md                                             # This Table of Contents & Quick Start Guide
├── 01_cleanroom_touchscreen_kiosk_operations.md          # Touchscreen UI, 6-card grid, tabs & Work Mode
├── 02_clinical_alarm_response_and_regulatory_lifecycle.md # Debounce timers, Pushover sirens, ack & audit log
└── 03_liquid_nitrogen_tank_dipstick_and_compliance.md    # 3-day manual checks, sawtooth charts & reports
```

### [Section 1: Cleanroom Touchscreen Kiosk Operations](01_cleanroom_touchscreen_kiosk_operations.md)
* **Gloved Operation & Hardware Profile:** Wall-mounted cleanroom touch panel designed for sterile gloved hands with oversized $\ge 60\text{px}$ targets.
* **Two-Tab Interface:** Instant client-side navigation between **Live Operations** (`/`) and **Cryo Suite** (`/cryo`).
* **Consolidated 6-Card Grid:** Live status for Cryo Tank 1, Cryo Tank 2, Medical Cold Storage (Fridge + Freezer combined), Cleanroom Ambient, Cleanroom Doors & Access, and dual side-by-side Chamber Incubators (Incubator 01 Ch 123 / Incubator 02 Ch 124).
* **Operational Session Mode:** Kiosk header pill and modal (`IN_SESSION` vs. `OFF_SESSION`) enabling intentional incubator alarm suppression during maintenance and changeovers while preserving cold storage and cryo monitoring.
* **Dual-Tab Audit Log:** Switch between `🚨 Alarms & Siren Log` and `🚪 Cleanroom Door Log` (`cleanroom_door_events`) with real-time open duration and session tags.
* **Compact Vertical LN2 Stepper:** Compact 135px 3-digit measurement box with vertical `+` (top) and `-` (bottom) increments and pre-populated previous checks.
* **Alarm States:** Normal green, amber pickup delay countdowns (`🟡 DELAY 2M / 3M`), flashing crimson siren banners with tap-to-silence targets, and steady green acknowledged banners.
* **Daily CAP Verification Banner:** Morning alarm pathway test button and immediate certification badge.
* **Touchscreen "Work Mode":** 15-minute temporary siren holdoff for routine sterile dish loading and batching.

---

### [Section 2: Clinical Alarm Response & Regulatory Lifecycle](02_clinical_alarm_response_and_regulatory_lifecycle.md)
* **Regulatory Compliance:** Adherence to CAP Reproductive Laboratory accreditation, CLIA '88 (42 CFR § 493.1252), and FDA 21 CFR Part 11 unalterable digital audit trails.
* **PLC On-Delay Debouncing:** Industrial timing filters (`tPickupDelay := T#2M` fridge, `T#3M` freezer/doors, `T#30S` cryo tanks) that suppress benign transient thermal dips from `alarm_events` while retaining continuous 1-minute historical traces in `mincopy_historical`.
* **Discrete Incubator Channels:** Channel 123 (Incubator 01) and Channel 124 (Incubator 02) with Off-Session suppression logic.
* **Comprehensive PostgreSQL Schemas:** Core schemas including `alarm_events`, `cleanroom_door_events`, `lab_operational_mode`, `cryo_maintenance_holds`, and `ln2_tank_logs`.
* **Two-Way Pushover Receipt Architecture:** Discrete per-alarm receipt tracking enables siren cancellation without silencing unrelated emergencies, paired with automatic silent team broadcasts.
* **Official 3-Page Monthly Compliance Report Packet (`/report/ln2`):** Automatic compilation of Tank 1, Tank 2, and cleanroom-wide Facility Alarms, Excursions & Quality Audit Sheet (Page 3).
* **Complete Operational Walkthrough:** Step-by-step timeline of an actual excursion from initial door opening, 2-minute trip, staff acknowledgment, door closure, and automatic resolution.
* **Auditor Queries:** Formatted SQL queries for equipment excursions, cleanroom door containment logs, and operational mode history.

---

### [Section 3: Liquid Nitrogen (LN2) Tank Dipstick & Compliance Auditing](03_liquid_nitrogen_tank_dipstick_and_compliance.md)
* **CAP/CLIA 3-Day Protocol:** Standard operating procedure for physical wooden ruler dipstick measurements on Cryo Tank 1 (Embryos) and Cryo Tank 2 (Sperm).
* **Compact Vertical Stepper UX:** High-contrast 135px 3-digit measurement layout with vertical `+0.5 / +1.0` and `-0.5 / -1.0` buttons, preventing lateral drift on touchscreen tablets and mobile phones.
* **Automatic Baseline Pre-Population:** Form automatically defaults to the last recorded manual measurement from `mod_arc_postgre_sql.ln2_tank_logs` with a `Previous check: XX.X cm` reference line.
* **Automatic Sensor Cross-Validation:** Automatic cross-checking of manual ruler readings against electronic depth sensors, flagging discrepancies $> 2.0\text{ cm}$.
* **60-Day Dual Sawtooth Evaporation Modeling:** Real-time boil-off velocity tracking (cm/day) comparing healthy baseline cycling against accelerated vacuum degradation.
* **Impending Vacuum Failure Protocol & Incident Case Study:** Operational response for Cryo Tank 2 vacuum breach, unrefilled downward plunge, specimen evacuation staging, and tank decommissioning.
* **3-Page Monthly Compliance Report Packet (`/report/ln2`):** High-resolution print-ready audit packet with interactive month selector, quick jump pills, and QA Director attestations.
* **Physical Cryo Tank Mute Pushbutton Plan:** Proposed WAGO digital I/O momentary tank-mounted pushbutton pausing alarms for 15 minutes during top-offs and specimen retrieval.

---

## Distinction Between User Manual and Engineering Notes

* **`user_manual/` (This Directory):** Intended for clinical staff, laboratory directors, embryologists, and accreditation inspectors. Focuses on system operation, SOP compliance, alarm response, and audit verification.
* **`notes/`:** Intended for internal engineering and IT administration. Contains hardware controller migration notes, MikroTik router scripts, network maps, and system credentials.

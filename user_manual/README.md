# IVF Laboratory SCADA: Cleanroom User Manual

Welcome to the **IVF Cleanroom SCADA & Environmental Monitoring System User Manual**. This manual serves as the operational guide for laboratory directors, clinical embryologists, technicians, and regulatory compliance inspectors at *Advanced Fertility of Alaska*.

---

## Quick System Access

* **Cleanroom Touchscreen Kiosk:** `http://192.168.10.133:8080/`
* **Cryo Tank Audit Suite:** `http://192.168.10.133:8080/cryo`
* **Printable Station QR Placard (For External Cryo Tanks):** `http://192.168.10.133:8080/print/qr`
* **Mobile LN2 Dipstick Entry (Smartphone QR Destination):** `http://192.168.10.133:8080/log` (select Tank 1 or Tank 2 on form)
* **Daily CAP Verification:** Accessible directly via the top banner on the Live Operations view.
* **1-Click LN2 Compliance Reports:**
  * Cryo Tank 1 (Embryos): `http://192.168.10.133:8080/report/ln2?tank=1`
  * Cryo Tank 2 (Sperm): `http://192.168.10.133:8080/report/ln2?tank=2`

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
* **Consolidated 6-Card Grid:** Live status for Cryo Tank 1, Cryo Tank 2, Medical Cold Storage (Fridge + Freezer combined), Cleanroom Ambient, Cleanroom Doors & Access, and Chamber Incubators.
* **Alarm States:** Normal green, amber pickup delay countdowns (`🟡 DELAY 2M / 3M`), flashing crimson siren banners with tap-to-silence targets, and steady green acknowledged banners.
* **Daily CAP Verification Banner:** Morning alarm pathway test button and immediate certification badge.
* **Touchscreen "Work Mode":** 15-minute temporary siren holdoff for routine sterile dish loading and batching.

---

### [Section 2: Clinical Alarm Response & Regulatory Lifecycle](02_clinical_alarm_response_and_regulatory_lifecycle.md)
* **Regulatory Compliance:** Adherence to CAP Reproductive Laboratory accreditation, CLIA '88 (42 CFR § 493.1252), and FDA 21 CFR Part 11 unalterable digital audit trails.
* **PLC On-Delay Debouncing:** Industrial timing filters (`tPickupDelay := T#2M` fridge, `T#3M` freezer/doors, `T#30S` cryo tanks) that suppress benign transient thermal dips from `alarm_events` while retaining continuous 1-minute historical traces in `mincopy_historical`.
* **Two-Way Pushover Receipt Architecture:** Discrete per-alarm receipt tracking enables siren cancellation without silencing unrelated emergencies, paired with automatic silent team broadcasts.
* **Complete Operational Walkthrough:** Step-by-step timeline of an actual excursion from initial door opening, 2-minute trip, staff acknowledgment, door closure, and automatic resolution.
* **Auditor Queries:** Formatted SQL queries to generate excursion inspection tables and correlated cooling traces.

---

### [Section 3: Liquid Nitrogen (LN2) Tank Dipstick & Compliance Auditing](03_liquid_nitrogen_tank_dipstick_and_compliance.md)
* **CAP/CLIA 3-Day Protocol:** Standard operating procedure for physical wooden ruler dipstick measurements on Cryo Tank 1 (Embryos) and Cryo Tank 2 (Sperm).
* **Touchscreen Logging Modal:** Fast numerical keypad entry on the kiosk, recording depth (cm), fill status, frost condition, and staff initials.
* **Automatic Sensor Cross-Validation:** Automatic cross-checking of manual ruler readings against electronic depth sensors, flagging discrepancies $> 2.0\text{ cm}$.
* **60-Day Dual Sawtooth Evaporation Modeling:** Real-time boil-off velocity tracking (cm/day) comparing healthy baseline cycling against accelerated vacuum degradation.
* **Impending Vacuum Failure Protocol & Incident Case Study:** Operational response for Cryo Tank 2 vacuum breach, unrefilled downward plunge, specimen evacuation staging, and tank decommissioning.
* **Automated PDF / Printable Compliance & Incident Reports:** Audit-ready 2-page reports with QA Director attestations for routine inspections and critical vessel failures.

---

## Distinction Between User Manual and Engineering Notes

* **`user_manual/` (This Directory):** Intended for clinical staff, laboratory directors, embryologists, and accreditation inspectors. Focuses on system operation, SOP compliance, alarm response, and audit verification.
* **`notes/`:** Intended for internal engineering and IT administration. Contains hardware controller migration notes, MikroTik router scripts, network maps, and system credentials.

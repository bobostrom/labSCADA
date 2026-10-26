# IVF Laboratory SCADA & Cleanroom Environmental Monitoring System

Automated deployment, industrial PLC telemetry integration, and regulatory compliance monitoring system for **Advanced Fertility of Alaska**. Integrates [Rapid SCADA](https://rapidscada.org), CODESYS industrial logic, PostgreSQL historical time-series storage, Pushover emergency siren dispatching, and a glove-friendly cleanroom touchscreen kiosk.

---

## Architecture & Core Features

- **Cleanroom Touchscreen Kiosk (`/`):** Wall-mounted operations dashboard designed for gloved embryologists with $\ge 60\text{px}$ touch targets, split Chamber Incubators (01 & 02), Operational Session Mode selector (`IN_SESSION` vs. `OFF_SESSION`), dual-tab audit log (`🚨 Alarms & Siren Log` vs `🚪 Cleanroom Door Log`), and 15-minute work mode siren holdoff.
- **Cryo Tank Audit Suite (`/cryo`):** Real-time level stat gauges, 3-day inspection countdown clocks, 60-day dual sawtooth evaporative models, and predictive vacuum failure detection.
- **Mobile QR LN2 Dipstick Logging (`/log`):** Mobile-optimized smartphone form scanned directly at the storage station with a compact vertical stepper (`+` top, 135px 3-digit box, `-` bottom), pre-populated baseline readings, visual neck seal checks, and laminated station placard generator (`/print/qr`).
- **3-Page Monthly Compliance Report Packet (`/report/ln2`):** Print-ready CAP/CLIA regulatory report packet with interactive month selector, Page 1 Cryo Tank 1 (Embryos), Page 2 Cryo Tank 2 (Sperm), and Page 3 Facility Alarms, Excursions & Quality Audit Sheet.
- **Multi-Tier PLC Debouncing:** Deterministic on-delay timing filters (`tPickupDelay := T#2M` fridge, `T#3M` freezer/doors, `T#30S` cryo tanks) in CODESYS suppress transient door-opening thermal dips from triggering false alarms while archiving raw continuous 1-minute traces.
- **Two-Way Emergency Siren Dispatch:** Pushover Priority 2 discrete sirens with per-alarm receipt tracking. Silencing at the kiosk or on a mobile phone immediately halts the alarm and sends a silent team notification to off-site directors.
- **PostgreSQL Database Storage (`mod_arc_postgre_sql`):** Comprehensive schema tracking `alarm_events`, `cleanroom_door_events`, `lab_operational_mode`, `cryo_maintenance_holds`, `ln2_tank_logs`, and continuous 365-day historical telemetry.
- **Hardware & Runtime Environment:** Battery-backed RTC sync (`hwclock`), ASP.NET Core Runtime 8.0/10.0, and Nginx reverse proxy on port 80 / 443.

---

## Quick System Access

Once installed, access the system directly in your browser:

* **Cleanroom Touchscreen Kiosk:** `http://<server-ip>/`
* **Cryo Tank Audit Suite:** `http://<server-ip>/cryo`
* **Monthly Compliance Report Packet (3 Pages):** `http://<server-ip>/report/ln2`
* **Mobile QR LN2 Dipstick Entry:** `http://<server-ip>/log`
* **Printable Station QR Placard:** `http://<server-ip>/print/qr`
* **Rapid SCADA Webstation:** `http://<server-ip>/scada/` (or port `10008`)
  - **Default Login:** `admin` / `scada`

---

## Installation & Setup

Run the automated installer script:

```bash
chmod +x install_rapidscada.sh
./install_rapidscada.sh
```

The script automatically configures:
1. Hardware RTC synchronization (disables `fake-hwclock`).
2. ASP.NET Core Runtime and system dependencies.
3. Rapid SCADA 6 daemons (`scadaserver6`, `scadacomm6`, `scadaweb6`, `scadaagent6`).
4. PostgreSQL database `rapid_scada` and schemas (`setup_channel_config.sql`, `setup_ln2_tracking.sql`, `setup_session_and_audit.sql`).
5. Nginx reverse proxy with SSL certificate and web assets.
6. IVF Alert Engine systemd service (`ivf-alert-engine.service`).

---

## Documentation & Manuals

* **📖 [Cleanroom User Manual](user_manual/README.md):** Complete operational user manual for clinical embryologists, laboratory directors, and CAP/CLIA accreditation inspectors:
  * [Chapter 1: Cleanroom Touchscreen Kiosk Operations](user_manual/01_cleanroom_touchscreen_kiosk_operations.md)
  * [Chapter 2: Clinical Alarm Response & Regulatory Lifecycle](user_manual/02_clinical_alarm_response_and_regulatory_lifecycle.md)
  * [Chapter 3: Liquid Nitrogen (LN2) Tank Dipstick & Compliance Auditing](user_manual/03_liquid_nitrogen_tank_dipstick_and_compliance.md)
* **📝 [Engineering Notes](notes/README.md):** Internal network maps, PLC architecture, WAGO pod wiring, credentials, and hardware mute button plans.
* **⚡ [CODESYS Integration](codesys/README.md):** IEC 61131-3 Function Blocks (`FB_PickupDropout`, `FB_AnalogAlarm`), simulator controls, and runtime setup.

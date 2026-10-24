# Liquid Nitrogen (LN2) Manual Dipstick & 3-Day Inspection Compliance Architecture

## 1. Executive Summary & Clinical Context
In human embryology and reproductive medicine cleanrooms, cryopreserved oocytes, embryos, and reproductive tissues are stored in liquid nitrogen (`LN2`) vapor or liquid phase tanks (`~ -150°C` to `-196°C`). Because cryogenic storage dewars naturally boil off nitrogen over time, they require systematic physical dipstick measurements and manual top-ups.

Historically, laboratories track this using physical paper clipboards hung on the tanks. This manual process introduces significant clinical, legal, and accreditation risks:
* **Clipboard Blind Spots:** Paper cannot alert anyone if a scheduled inspection is missed over a holiday, weekend, or busy clinical shift.
* **Accreditation Exposure:** CAP (College of American Pathologists), CLIA, and Joint Commission inspectors mandate strict, continuous, and tamper-proof verification of all storage vessel checks.
* **Vacuum Insulation Failure:** A gradual loss of dewar vacuum insulation results in accelerated boil-off rates before temperatures rise. Paper logs rarely compute daily burn rates (`Δ cm / day`), masking impending vacuum failure until temperatures spike.

This architecture transitions the laboratory from paper tracking to a **fully digital, glove-friendly cleanroom kiosk workflow** integrated into the SCADA alert controller and Grafana monitoring suite.

---

## 2. System Architecture Overview

```
                      ┌─────────────────────────────────────────┐
                      │    Embryology Staff (Cleanroom Suite)   │
                      └────────────────────┬────────────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        ▼                                     ▼
             [Wall Kiosk Display]                  [Phone via Tank QR Code]
             http://scadapi02.local:8080           http://scadapi02.local:8080
                        │                                     │
                        └──────────────────┬──────────────────┘
                                           │
                                           ▼ POST /api/ln2_log
                        ┌─────────────────────────────────────┐
                        │ IVF Alert Engine & Web Controller   │
                        │ (ivf_alert_engine.py :8080)         │
                        └──────┬────────────────────────┬─────┘
                               │                        │
         Writes Audit Record   │                        │ Priority 2 Siren (if Overdue)
                               ▼                        ▼ Priority 0 Chime (on Log)
              ┌─────────────────────────────┐   ┌─────────────────────────────┐
              │ PostgreSQL Database         │   │ Pushover API Client         │
              │ mod_arc_postgre_sql         │   │ (Discrete Receipt Tracking) │
              │ .ln2_tank_logs              │   └──────────────┬──────────────┘
              └──────────────┬──────────────┘                  │
                             │                                 ▼
                             ▼ Read Queries          [On-Call Physician / Staff]
              ┌─────────────────────────────┐        Emergency siren silence
              │ Grafana Kiosk & Dashboards  │        directly from phone screen
              │ (Port 3000 & Grafana Cloud) │
              └─────────────────────────────┘
```

---

## 3. Glove-Friendly Cleanroom Touchscreen UX (Port `:8080`)

Technicians and embryologists work gloved in sterile attire and cannot manipulate delicate on-screen mobile keyboards. The inspection interface at `http://<server-ip>:8080` provides high-contrast, oversized touch targets:

### Touchscreen Inspection Dialog
```text
╔═════════════════════════════════════════════════════════════════════════╗
║ 🧊 RECORD LN2 DIPSTICK CHECK                                         ✕  ║
║ Resets 3-day inspection clock upon submission                           ║
╟─────────────────────────────────────────────────────────────────────────╢
║ TANK IDENTIFIER                                                         ║
║ [ Cryo Tank 1 (Embryos) ]*   [ Cryo Tank 2 (Sperm) ]                    ║
║                                                                         ║
║ DIPSTICK LEVEL (CM)                                                     ║
║ ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌─────────┐ ║
║ │  - 1.0   │  │  - 0.5   │  │   21.5 cm    │  │  + 0.5   │  │ + 1.0   │ ║
║ └──────────┘  └──────────┘  └──────────────┘  └──────────┘  └─────────┘ ║
║                                                                         ║
║ NITROGEN ADDED / TOPPED OFF?                                            ║
║ ┌────────────────────────────────┐  ┌─────────────────────────────────┐ ║
║ │ 🔘 No (Level Check Only)       │  │ 🔵 Yes (Tank Filled to Full)    │ ║
║ └────────────────────────────────┘  └─────────────────────────────────┘ ║
║                                                                         ║
║ STAFF INITIALS                                                          ║
║ [ BO ]   [ SJ ]   [ AK ]   [ TL ]     [ Type Custom Initials: _____ ]   ║
║                                                                         ║
║ VISUAL INSPECTION / NECK SEAL                                           ║
║ [ Normal / Good Seal ]*   [ Neck Frost Detected ]   [ Vacuum Concern ]  ║
║                                                                         ║
║ NOTES (OPTIONAL)                                                        ║
║ [ e.g. routine 3-day top-off, inspected o-ring gasket                 ] ║
║                                                                         ║
║ ┌─────────────────────────────────────────────────────────────────────┐ ║
║ │                      ✅ SUBMIT INSPECTION                           │ ║
║ └─────────────────────────────────────────────────────────────────────┘ ║
╚═════════════════════════════════════════════════════════════════════════╝
```

---

## 4. External Tank Monitoring & Mobile QR Code Workflow (For Non-Lab & Support Staff)

### Operational Context: Tanks Outside the Cleanroom Suite
At *Advanced Fertility of Alaska*, the cryogenic storage dewars (**Cryo Tank 1: Embryos** and **Cryo Tank 2: Sperm**) are physically located side-by-side in the secure cryogenic corridor **outside the main cleanroom laboratory**:
* **Support Personnel Access:** Non-laboratory staff (clinical nurses, medical assistants, facilities technicians, on-call support) frequently perform or assist with the routine Monday / Wednesday / Friday level verifications.
* **Gowning Barrier:** These staff members do not gown up into sterile cleanroom bunny suits to access the cleanroom touchscreen kiosk.
* **Single Unified Placard:** Because both dewars stand immediately next to each other, a single, durable laminated **Cryogenic Storage Station Placard** is posted at eye level between the two tanks. A single QR code provides instant access to both tanks.

```
                  ┌──────────────────────────────────────────────┐
                  │ Staff walks up to Cryo Station outside lab   │
                  │ (Cryo Tank 1: Embryos & Cryo Tank 2: Sperm)  │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ 1. Put on cryo gloves and protective shield  │
                  │ 2. Insert measuring stick into Tank 1 (5s)   │
                  │ 3. Wave stick in air & read frost line (cm)  │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ 4. Scan Single Station QR Code with Phone    │
                  │    • Destination URL: http://<host>/log      │
                  │    • No app download or login required       │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ 5. Select Tank & Submit:                     │
                  │    • Tap "Cryo Tank 1" or "Cryo Tank 2" tab  │
                  │    • Use compact vertical stepper for level  │
                  │    • Tap staff initials & tap "Submit"       │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ 6. Log Adjacent Tank (30-Second Workflow):   │
                  │    • Measure second tank with dipstick       │
                  │    • Tap "Log Another Tank" on confirmation  │
                  │    • Form auto-flips to the other tank       │
                  │    • Enter level and submit                  │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ 7. Immediate System Sync:                    │
                  │    • Saved to PostgreSQL `ln2_tank_logs`     │
                  │    • Kiosk resets 3-day countdown timer      │
                  │    • Pushover alert dispatched to Directors  │
                  │    • Overdue schedule alarm auto-cleared     │
                  └──────────────────────────────────────────────┘
```

### Mobile Web Form (`/log`)
Scanning the station QR code opens a mobile-optimized card directly on any iOS or Android smartphone browser (no app download or login required on the clinic Wi-Fi network):
* **Dual Tank Switcher:** Prominent tabs at the top allow selecting between **Cryo Tank 1 (Embryos)** and **Cryo Tank 2 (Sperm)** with a single touch.
* **Live Telemetry Comparison:** Displays the active tank's real-time electronic vapor temperature (e.g. `-196.2°C`) and electronic depth sensor reading, allowing staff to perform an instant sanity check against their physical ruler reading.
* **Compact Vertical Stepper:** A narrow, thumb-friendly vertical keypad optimized for one-handed operation on mobile screens (`+0.5` / `+1.0` buttons on top, centered high-contrast level display with `cm` badge, `-0.5` / `-1.0` buttons below).
* **Quick Initials / Staff Identifier:** Includes quick chips for clinical staff (`BO`, `SJ`, `AK`, `TL`, `RN`, `Facilities`) and a text box for custom names.
* **Instant Confirmation & Quick Sequential Reset:** Upon tapping **Submit**, the form validates the input, stores the record in PostgreSQL, and displays a green confirmation receipt. Tapping **"Log Another Tank"** automatically toggles the active tank so the adjacent tank can be inspected and recorded without rescanning.

### Printing the Laminated Station Placard (`/print/qr`)
To print the unified placard for mounting between the physical tanks:
1. Open **`http://192.168.10.133:8080/print/qr`** in any web browser (or click **📱 Print Station QR Placard** on the Kiosk Cryo Suite tab).
2. The page renders a single, high-contrast station placard formatted for standard 8.5" x 11" letter paper:
   * **Dual Tank Badges:** Clear labeling for Cryo Tank 1 (Embryos) and Cryo Tank 2 (Sperm).
   * **Unified Vector QR Code:** High-resolution SVG pointing directly to `http://<host>/log`.
   * **Step-by-Step SOP:** 6-step clinical standard operating procedure including PPE, dipstick measurement, tank selection, and adjacent tank logging.
   * **Regulatory Compliance Notice:** CAP / CLIA / JCAHO documentation disclaimer and critical 10.0 cm safety thresholds.
3. Click the blue **`[ 🖨️ Print Laminated Station Placard ]`** button (or press `Ctrl + P`).
4. Print in color, laminate the sheet to resist cryogenic condensation, and affix the placard at eye level on the wall or safety rail directly between the two tanks.

---

## 5. PostgreSQL Audit Trail Schema

All records are written to table `mod_arc_postgre_sql.ln2_tank_logs` in the `rapid_scada` database:

```sql
CREATE TABLE mod_arc_postgre_sql.ln2_tank_logs (
    id SERIAL PRIMARY KEY,
    tank_id VARCHAR(32) NOT NULL DEFAULT 'Cryo Tank 1',
    level_cm NUMERIC(5, 2) NOT NULL,
    was_filled BOOLEAN DEFAULT FALSE,
    frost_condition VARCHAR(32) DEFAULT 'Good',
    initials VARCHAR(16) NOT NULL,
    notes TEXT,
    logged_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ln2_tank_logs_tank_time 
ON mod_arc_postgre_sql.ln2_tank_logs (tank_id, logged_at DESC);

-- Permissions for Grafana telemetry proxy
GRANT SELECT, INSERT, UPDATE ON mod_arc_postgre_sql.ln2_tank_logs TO grafana_reader;
GRANT USAGE, SELECT ON SEQUENCE mod_arc_postgre_sql.ln2_tank_logs_id_seq TO grafana_reader;
```

### Compliance Inspection Report
When CAP or CLIA surveyors conduct an inspection, a single SQL query produces an exportable regulatory log:

```sql
SELECT 
    logged_at AS "Inspection Time",
    tank_id AS "Tank ID",
    ROUND(level_cm, 1)::text || ' cm' AS "Dipstick Level",
    CASE WHEN was_filled THEN 'Yes (Filled)' ELSE 'Level Check Only' END AS "Filled?",
    frost_condition AS "Seal Condition",
    initials AS "Staff Initials",
    COALESCE(notes, '-') AS "Notes"
FROM mod_arc_postgre_sql.ln2_tank_logs
ORDER BY logged_at DESC;
```

---

## 6. The Mon / Wed / Fri 5:00 PM Escalation Lifecycle

A background thread (`ln2_schedule_watcher`) in [ivf_alert_engine.py](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py) evaluates compliance against the clinical **Monday, Wednesday, Friday by 5:00 PM** cleanroom schedule every 60 seconds.

```text
 ┌───────────────────────┬───────────────────────────────────────────┬────────────────────────────────────────────┐
 │ Day of Week           │ Time / Condition                          │ Kiosk Display / Pushover Escalation        │
 ├───────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────────┤
 │ Mon, Wed, or Fri      │ Midnight to 5:00 PM (Unchecked)           │ 🟡 DUE TODAY: Dipstick check due 5pm       │
 │ Mon, Wed, or Fri      │ Logged by staff                           │ 🟢 COMPLETED: Today's check logged         │
 │ Mon, Wed, or Fri      │ After 5:00 PM without log                 │ ⚠️ OVERDUE: Priority 1 Warning (Rings Once)│
 │ Tue, Thu, Sat, or Sun │ Previous required check was satisfied     │ 🟢 ON SCHEDULE: Next check: [Day] 5pm      │
 │ Tue, Thu, Sat, or Sun │ Previous required check was missed        │ ⚠️ OVERDUE: 8:00 AM Morning Rounds Reminder│
 └───────────────────────┴───────────────────────────────────────────┴────────────────────────────────────────────┘
```

### 4-Tier Clinical Alarm Taxonomy & Escalation States

| Priority Level | Classification | Trigger Scenarios | Mobile & Kiosk Behavior |
| :--- | :--- | :--- | :--- |
| **`Priority 2` (Emergency)** | Critical Specimen Excursion | Chamber temp excursion (Fridge > 8°C, Freezer > -15°C, Cryo Tank > -135°C), Door open > 3m. | **Continuous repeating siren** (retries every 60s for 2h until phone lock-screen ack). Escalate after 30 min if chamber remains out of range. |
| **`Priority 1` (High)** | Operational & Compliance Warning | Mon/Wed/Fri LN2 dipstick check unlogged by 5:00 PM; Cleanroom ambient drift. | **Single distinct warning chime** (`intermission`). Rings once, bypasses quiet hours, **no repeating siren**. Re-alerted via **8:00 AM Morning Shift Sweep** if unlogged. |
| **`Priority 0` (Normal)** | Shift Hand-offs & Resolutions | Dipstick check logged, alarm resolved (`🟢 RESOLVED`), daily 9:00 AM QA pathway test. | Single pleasant chime (`magic`). Respects device quiet hours. |
| **`Priority -1` (Low/Silent)** | Diagnostic Telemetry & Audits | Background watchdog pings, backup completions. | Silent badge update in Pushover app; no vibration or screen wake. |

---

## 7. Web & REST API Endpoints

The HTTP server running on port `8080` provides dedicated web and REST endpoints:

### 1. `GET /log` (optional `?tank=1` or `?tank=2`)
Mobile-first web application for phone scanning at the cryogenic storage station. Features instant dual-tank switcher, live electronic telemetry comparison, compact vertical stepper, nitrogen top-off toggle, staff initials chips, and visual neck seal checks. Automatically prompts to log the second tank upon confirmation.

### 2. `GET /print/qr` (or `/qr`)
Generates a print-ready 8.5" x 11" laminated Cryogenic Storage Station Placard featuring a single unified vector SVG QR code, dual tank identifiers, and standard operating procedures. Dedicated vector SVG endpoints are available at `/qr/station.svg` (or `/qr.svg`).

### 3. `GET /api/ln2_status`
Returns the latest inspection status and the 10 most recent logs in JSON format.

### 4. `POST /api/ln2_log`
Accepts a new dipstick measurement, resets the 72-hour timer, and cancels active overdue alarms.
* **Headers:** `Content-Type: application/json`
* **Body:**
```json
{
  "tank_id": "Cryo Tank 1",
  "level_cm": 21.5,
  "was_filled": false,
  "frost_condition": "Good",
  "initials": "BO",
  "notes": "Routine 3-day level check"
}
```

---

## 8. Grafana Telemetry & Boil-Off Visualization

In [grafana_ivf_lab_dashboard.json](file:///home/bobostrom/Projects/labSCADA/grafana_ivf_lab_dashboard.json) (Port `3000`), a dedicated section provides continuous visual compliance:

### 1. Stat Gauge Panel: `Cryo Tank 1: Current Dipstick & 3-Day Clock`
* Displays current level in `cm` alongside `Hours Since Check`.
* Color thresholds:
  * **Green:** `< 60 hours`
  * **Amber:** `60 – 71.9 hours`
  * **Red:** `≥ 72 hours`

### 2. Table Panel: `LN2 Dipstick Regulatory Inspection Log (CAP/CLIA Audit Trail)`
* Queries `mod_arc_postgre_sql.ln2_tank_logs` with formatted timestamps, dipstick levels in cm, fill status icons, staff initials, and visual neck seal checks.

### 3. Sawtooth Boil-Off Rate Modeling (Predictive Early Warning)
Because levels are logged digitally every 3 days, natural LN2 evaporation produces a sawtooth chart:
* **Nominal Daily Loss:** `~0.8 cm to 1.2 cm / day` (depending on dewar geometry).
* **Vacuum Degradation Threshold:** If the dipstick level drops `> 2.5 cm / day`, the system detects rapid loss of vacuum before internal vapor temperatures rise above `-135°C`.

---

## 9. Diagnostic & Management Commands

### Check Alert Engine & Scheduler Status
```bash
systemctl status ivf-alert-engine.service --no-pager
```

### Tail Live Alert Engine Logs
```bash
journalctl -u ivf-alert-engine.service -f
```

### Direct PostgreSQL Query for LN2 Records
```bash
PGPASSWORD=postgres psql -h localhost -U postgres -d rapid_scada -c \
  "SELECT id, tank_id, level_cm, was_filled, initials, logged_at FROM mod_arc_postgre_sql.ln2_tank_logs ORDER BY id DESC LIMIT 10;"
```

---

## 10. Related User Manual Sections

* **Cleanroom Touchscreen Kiosk Operations:** [01_cleanroom_touchscreen_kiosk_operations.md](file:///home/bobostrom/Projects/labSCADA/user_manual/01_cleanroom_touchscreen_kiosk_operations.md) — Covers the physical touchscreen kiosk, 2-tab navigation (`/` and `/cryo`), 6-card dashboard layout, glove-friendly tap targets, and daily CAP verification banner.
* **Clinical Alarm Architecture & Regulatory Lifecycle:** [02_clinical_alarm_response_and_regulatory_lifecycle.md](file:///home/bobostrom/Projects/labSCADA/user_manual/02_clinical_alarm_response_and_regulatory_lifecycle.md) — Detailed regulatory rationale (CAP/CLIA), PLC debouncing algorithms, Pushover receipt architecture, PostgreSQL schema, and complete operational walkthroughs.
* **Alert Engine Implementation:** [ivf_alert_engine.py](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py) — The Python service handling telemetry scanning, Pushover dispatch/cancellation, and web kiosk hosting on port 8080.

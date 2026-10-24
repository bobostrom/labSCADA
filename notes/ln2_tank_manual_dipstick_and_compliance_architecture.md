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

### QR Code Tank Tagging
Each tank can feature an encrypted or direct local URL sticker:
```text
http://scadapi02.local:8080/?action=dipstick&tank=Cryo%20Tank%201
```
Scanning this QR code with an iPad or mobile phone launches the form with **Cryo Tank 1** pre-selected, allowing instant logging without room-to-room transit.

---

## 4. PostgreSQL Audit Trail Schema

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

## 5. The 3-Day (72-Hour) Escalation Lifecycle

A background thread (`ln2_schedule_watcher`) in [ivf_alert_engine.py](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py) evaluates the elapsed duration since the last log for every active tank every 60 seconds:

```
  0h                                60h                           72h (3 Days)
──┼──────────────────────────────────┼─────────────────────────────┼──────────────►
 Logged                          Due Warning                   OVERDUE SIREN
• Clock starts              • Amber card on :8080         • Flashing Red on Kiosk
• Green on Kiosk            • "Due within 12h"            • Priority 2 Emergency Siren
• Resets timer              • Informational notice          via Pushover to team
```

### Escalation States

| State | Window | Cleanroom Kiosk UI | Pushover Alerting |
| :--- | :--- | :--- | :--- |
| **🟢 Normal** | `0h – 60h` | Card shows `CLOCK OK` with level (cm) and hours elapsed. | Silent. |
| **🟡 Due Warning** | `60h – 72h` | Card turns Amber: `🟡 DUE TODAY (64h)`. | Optional low-priority informational chime once per shift. |
| **🔴 OVERDUE** | `≥ 72h` | Flashing red banner: `🔴 OVERDUE: Cryo Tank 1 has NOT been inspected in > 72 hours!`. | **Priority 2 Repeating Siren** (retries every 60s for 2 hours) with discrete receipt tracking. |
| **🟢 Auto-Reset** | *On Submit* | Instantly returns to Green. | Silences emergency siren, cancels Pushover receipt, and sends `🟢 RESOLVED` broadcast. |

---

## 6. REST API Endpoints

The HTTP server running on port `8080` provides dedicated REST endpoints:

### 1. `GET /api/ln2_status`
Returns the latest inspection status and the 10 most recent logs.
* **Request:** `GET http://127.0.0.1:8080/api/ln2_status`
* **Response:**
```json
{
  "tanks": {
    "Cryo Tank 1": {
      "tank_id": "Cryo Tank 1",
      "level_cm": 21.5,
      "was_filled": false,
      "frost_condition": "Good",
      "initials": "BO",
      "notes": "Dipstick verification test",
      "logged_at": "2026-10-23 19:39:14.905524-08",
      "hours_since": 0.1,
      "status": "NORMAL"
    }
  },
  "history": [
    {
      "id": 2,
      "tank_id": "Cryo Tank 1",
      "level_cm": 21.5,
      "was_filled": false,
      "frost_condition": "Good",
      "initials": "BO",
      "notes": "Dipstick verification test",
      "logged_at": "2026-10-23 19:39:14.905524-08"
    }
  ]
}
```

### 2. `POST /api/ln2_log`
Accepts a new dipstick measurement, resets the 72-hour timer, and cancels active overdue alarms.
* **Request:** `POST http://127.0.0.1:8080/api/ln2_log`
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
* **Response:**
```json
{
  "success": true,
  "log_id": 2,
  "message": "Recorded 21.5 cm for Cryo Tank 1 by BO."
}
```

---

## 7. Grafana Telemetry & Boil-Off Visualization

In [grafana_ivf_lab_dashboard.json](file:///home/bobostrom/Projects/labSCADA/grafana_ivf_lab_dashboard.json) (Port `3000`), a dedicated section provides continuous visual compliance:

### 1. Stat Gauge Panel: `Cryo Tank 1: Current Dipstick & 3-Day Clock`
* Displays current level in `cm` alongside `Hours Since Check`.
* Color thresholds:
  * **Green:** `< 60 hours`
  * **Amber:** `60 – 71.9 hours`
  * **Red:** `≥ 72 hours`
* Includes a direct clickable link to `http://scadapi02.local:8080/` to launch the entry modal.

### 2. Table Panel: `LN2 Dipstick Regulatory Inspection Log (CAP/CLIA Audit Trail)`
* Queries `mod_arc_postgre_sql.ln2_tank_logs` with formatted timestamps, dipstick levels in cm, fill status icons, staff initials, and visual neck seal checks.

### 3. Sawtooth Boil-Off Rate Modeling (Predictive Early Warning)
Because levels are logged digitally every 3 days, natural LN2 evaporation produces a sawtooth chart:
* **Nominal Daily Loss:** `~0.8 cm to 1.2 cm / day` (depending on dewar geometry).
* **Vacuum Degradation Threshold:** If the dipstick level drops `> 2.5 cm / day`, the system detects rapid loss of vacuum before internal vapor temperatures rise above `-135°C`.

---

## 8. Diagnostic & Management Commands

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

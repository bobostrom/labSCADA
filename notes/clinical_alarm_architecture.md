# IVF Clinical Alarm Architecture & Regulatory Lifecycle

## 1. Executive Summary & Clinical Regulatory Context

In an Assisted Reproductive Technology (ART) and embryology cleanroom suite, cryogenic storage, medical refrigeration, and chamber incubators safeguard irreplaceable human gametes and embryos. Operational realities dictate strict requirements for alarm handling:

* **Sterile Field Integrity:** Technicians and embryologists work gloved under laminar flow hoods during delicate micromanipulation (ICSI, biopsying, embryo grading). Staff cannot and should not deglove, handle personal mobile phones, or navigate apps to silence alarms during active sterile procedures.
* **Transient vs. True Excursions:** Opening refrigerator or incubator doors for dish loading, specimen retrieval, or media equilibration naturally introduces transient ambient air mixing and temperature fluctuations. These brief operational dips are expected and clinically benign.
* **Regulatory Compliance Requirements:**
  * **CAP (College of American Pathologists) Reproductive Laboratory Accreditation:** Mandates continuous monitoring, defined operational tolerances, verified alarm pathways, and tamper-proof excursion documentation.
  * **CLIA '88 (42 CFR § 493.1252):** Requires documentation of all equipment failures, environmental excursions, and documented corrective actions taken.
  * **FDA 21 CFR Part 11:** Requires complete, unalterable digital audit trails featuring precise timestamps, operator attribution, and secure archiving.
* **Architectural Pillars:**
  1. **Nuisance Alarm Prevention:** Multi-tier PLC debouncing suppresses transient door-opening thermal dips from escalating off-site.
  2. **Two-Way Pushover Receipt Architecture:** Discrete per-alarm receipt tracking enables siren cancellation without silencing unrelated emergencies.
  3. **Touchscreen Kiosk Integration:** Direct wall-mounted glove-friendly interaction in the cleanroom allows immediate silencing and team peace of mind.
  4. **PostgreSQL Audit Trail:** Complete lifecycle tracking (trigger, acknowledgment, restabilization duration) permanently recorded in the SCADA database.

---

## 2. Multi-Tiered Alarm Debouncing & PLC Filtering

To eliminate false emergency alerts while ensuring fail-safe detection of genuine equipment breakdowns, alarm debouncing is handled directly at the deterministic controller layer (WAGO PFC200 PLC running IEC 61131-3 logic in [PLC_PRG.st](file:///home/bobostrom/Projects/labSCADA/codesys/src/PLC_PRG.st)):

```
                       ┌───────────────────────────────┐
                       │ Analog Sensor (e.g. Ch 112)   │
                       │ Exceeds Operational Threshold │
                       └───────────────┬───────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │ WAGO PLC On-Delay Timer (TON) │
                       │ tPickupDelay (2M / 3M / 30S)  │
                       └───────────────┬───────────────┘
                                       │
                      Temp recovers    │   Temp remains out of range
                      within window    │   for duration of timer
                            │          │
                            ▼          ▼
                 ┌──────────────────┐ ┌──────────────────────────────┐
                 │ Timer Resets     │ │ Discrete Alarm Bit Trips     │
                 │ bAlarm = FALSE   │ │ bAlarm = TRUE (e.g. Ch 123)  │
                 └────────┬─────────┘ └──────────────┬───────────────┘
                          │                          │
                          ▼                          ▼
               ┌───────────────────────┐ ┌───────────────────────────┐
               │ No Alarm Dispatched   │ │ IVF Alert Engine Triggers │
               │ Continuous Trace in   │ │ Priority 2 Siren & DB Row │
               │ `mincopy_historical`  │ │ in `alarm_events`         │
               └───────────────────────┘ └───────────────────────────┘
```

### Configured Equipment Delay Filters

| Equipment | Analog Temp Channel | Discrete Alarm Channel | Pickup Delay (`tPickupDelay`) | Clinical Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Medical Freezer** | Ch 111 (`rMedFreezerTemp`) | Ch 124 (`bMedFreezerAlarm`) | **3 Minutes** (`T#3M`) | Deep cold storage thermal inertia; accommodates daily inventory checks. |
| **Medical Refrigerator** | Ch 112 (`rMedFridgeTemp`) | Ch 123 (`bMedFridgeAlarm`) | **2 Minutes** (`T#2M`) | Refrigerator air mix recovers rapidly; 2 minutes filters normal door access. |
| **Cryo Tank 1 (Embryos)** | Ch 125 / Ch 113 (`rCryoTank1Temp`) | Ch 126 (`bCryoTank1Alarm`) | **30 Seconds** (`T#30S`) | Liquid nitrogen vapor requires immediate warning upon thermal rise. |
| **Cryo Tank 2 (Sperm)** | Ch 104 / Ch 114 (`rCryoTank2Temp`) | Ch 127 (`bCryoTank2Alarm`) | **30 Seconds** (`T#30S`) | Immediate warning upon vapor elevation or level depletion. |
| **Cleanroom Doors** | — | Ch 121 / Ch 122 (`bDoor01/02_Alarm`) | **3 Minutes** (`T#3M`) | Allows standard personnel entry/exit and cart transfer without nuisance sirens. |

### Transient Dip Suppression Policy
* **Regulatory Consensus:** Thermal fluctuations that recover within the PLC pickup delay window are intentionally **suppressed from generating entries in `mod_arc_postgre_sql.alarm_events`**.
* **Clinical Purpose:** Prevents alarm fatigue, eliminates superfluous paperwork, and keeps the clinical audit trail reserved strictly for actionable emergencies.
* **Audit Assurance:** Continuous 1-minute historical time-series data is retained in `mod_arc_postgre_sql.mincopy_historical` for 365 days. Inspectors can inspect raw temperature curves at any time, proving equipment integrity.

---

## 3. Two-Way Pushover Receipt Architecture

Generic notification systems that use broadcast tags (e.g., `tags=ivf_alarm`) are dangerous in clinical environments because silencing one alarm can inadvertently silence an unrelated, active emergency elsewhere in the laboratory.

The [ivf_alert_engine.py](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py) engine employs **discrete receipt tracking**:

```
[Alarm Detected] ──► POST /1/messages.json (Priority=2, retry=30, expire=3600)
                            │
                            ▼ Returns { "receipt": "r9a8b7c6d5" }
                     ┌──────────────────────────────────┐
                     │ Save to PostgreSQL `alarm_events`│
                     │ (pushover_receipt = 'r9a8b7c6d5')│
                     └──────────────┬───────────────────┘
                                    │
               ┌────────────────────┴────────────────────┐
               │                                         │
       [Cleanroom Kiosk Tap]                     [Mobile Phone Ack]
               │                                         │
               ▼                                         ▼
   POST /1/receipts/cancel/r9a8b...            Pushover API records
   (Cancels this specific siren)               acknowledged_by user token
               │                                         │
               └────────────────────┬────────────────────┘
                                    │
                                    ▼
                      UPDATE PostgreSQL `alarm_events`
                      - is_acknowledged = true
                      - acknowledged_by = 'Dr. Ostrom' (or 'Lab Kiosk')
                      - acknowledged_by_token = user_token
                      - acknowledged_at = NOW()
                                    │
                                    ▼
                      Send Silent Team Broadcast (Priority=0)
                      "🔕 ALARM ACKNOWLEDGED: Medical Refrigerator...
                       Siren silenced. Staff attending."
```

### Safety Advantages
1. **Emergency Isolation:** Silencing a refrigerator door alarm will **never** silence a concurrent cryo tank alert or incubator excursion.
2. **Accountability:** The database captures the specific responder's name and token, whether acknowledged from an iPhone lock screen, Android notification, or the in-cleanroom touchscreen kiosk.
3. **Team Peace of Mind:** When an in-lab embryologist acknowledges an alarm at the kiosk, an immediate silent notification is sent to all off-site team members so directors know the issue is under active management.

---

## 4. PostgreSQL Schema & Database Architecture

All data resides in PostgreSQL under the `mod_arc_postgre_sql` schema in database `rapid_scada`.

### Complete Table Architecture

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│     curcopy_current             │       │     mincopy_historical          │
├─────────────────────────────────┤       ├─────────────────────────────────┤
│ cnl_num (INT)                   │       │ cnl_num (INT)                   │
│ val (DOUBLE)                    │       │ d_time (TIMESTAMPTZ)            │
│ stat (INT)                      │       │ val (DOUBLE)                    │
│ d_time (TIMESTAMPTZ)            │       │ stat (INT)                      │
├─────────────────────────────────┤       ├─────────────────────────────────┤
│ Real-time live snapshot         │       │ 1-minute historical time series │
│ Flushed every 2 seconds         │       │ 365-day retention               │
└─────────────────────────────────┘       └─────────────────────────────────┘
                 │                                         │
                 └────────────────────┬────────────────────┘
                                      │
                                      ▼
                      ┌─────────────────────────────────┐
                      │     alarm_events                │
                      ├─────────────────────────────────┤
                      │ id (SERIAL PRIMARY KEY)         │
                      │ cnl_num (INT)                   │
                      │ equipment_name (VARCHAR)        │
                      │ alarm_type (VARCHAR)            │
                      │ excursion_val (DOUBLE)          │
                      │ triggered_at (TIMESTAMPTZ)      │
                      │ pushover_receipt (VARCHAR)      │
                      │ is_acknowledged (BOOLEAN)       │
                      │ acknowledged_by (VARCHAR)       │
                      │ acknowledged_by_token (VARCHAR) │
                      │ acknowledged_at (TIMESTAMPTZ)   │
                      │ is_resolved (BOOLEAN)           │
                      │ resolved_at (TIMESTAMPTZ)       │
                      │ duration_seconds (INT)          │
                      │ priority (INT)                  │
                      │ corrective_action_notes (TEXT)  │
                      ├─────────────────────────────────┤
                      │ Discrete clinical audit log     │
                      │ Permanent, immutable records    │
                      └─────────────────────────────────┘
```

### Table DDL: `mod_arc_postgre_sql.alarm_events`
```sql
CREATE TABLE IF NOT EXISTS mod_arc_postgre_sql.alarm_events (
    id SERIAL PRIMARY KEY,
    cnl_num INTEGER NOT NULL,
    equipment_name VARCHAR(64) NOT NULL,
    alarm_type VARCHAR(64) NOT NULL,
    excursion_val DOUBLE PRECISION,
    triggered_at TIMESTAMPTZ NOT NULL,
    pushover_receipt VARCHAR(64),
    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(64),
    acknowledged_by_token VARCHAR(64),
    acknowledged_at TIMESTAMPTZ,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    priority INTEGER DEFAULT 2,
    corrective_action_notes TEXT
);

GRANT USAGE ON SCHEMA mod_arc_postgre_sql TO grafana_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA mod_arc_postgre_sql TO grafana_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA mod_arc_postgre_sql GRANT SELECT ON TABLES TO grafana_reader;
```

---

## 5. End-to-End Operational Walkthrough: Medical Fridge Excursion

This section details exactly what happens across the physical hardware, PLC, SCADA, alert engine, and database during an excursion event.

### Scenario Timeline
1. **Refrigerator door is left open.**
2. Temperature rises above the $+8.0^\circ\text{C}$ threshold.
3. After 2 minutes, the PLC on-delay timer completes and triggers an official excursion.
4. Priority 2 Pushover emergency sirens are dispatched to staff phones; lab kiosk enters flashing alarm state.
5. A user acknowledges the alarm (via kiosk or phone); repeating siren halts and team notification broadcasts.
6. The user closes the refrigerator door.
7. Refrigerator cools down below $+8.0^\circ\text{C}$; event is automatically resolved and a resolution notification is sent.

---

### Step-by-Step System & Database Action Matrix

| Phase | Time | System State | Rapid SCADA & PLC | Alert Engine & Pushover | Database Action (`rapid_scada`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Door Ajar & Warm Up** | $T_0 = 13:30:00$ | Door opens. Air temp reaches $+8.4^\circ\text{C}$. | Ch 112 = 8.4°C. PLC timer `fbFridgeAlarm.TON` starts. Ch 123 (`bMedFridgeAlarm`) = 0. | Kiosk badge turns `🟡 DELAY (2M)`. No Pushover alerts. | **`curcopy_current`:** Ch 112 updated to 8.4.<br>**`mincopy_historical`:** Logs 8.4°C at 13:31:00.<br>**`alarm_events`:** **0 rows written.** (Transient dip suppressed). |
| **2. Excursion Trip** | $T_1 = 13:32:00$<br>($T_0 + 2\text{m}$) | Temp has remained $>8.0^\circ\text{C}$ for 2m (now $+9.8^\circ\text{C}$). | PLC timer completes: `fbFridgeAlarm.bAlarm` $\rightarrow$ `TRUE`. Ch 123 $\rightarrow$ 1. | IVF Alert Engine sends Priority 2 siren with receipt `r7k9m2x4v1`. Kiosk flashes red banner. | **`alarm_events`:** **NEW ROW INSERTED** (id=33, is_acknowledged=FALSE, is_resolved=FALSE).<br>See [SQL Insert](#sql-insert-at-trip) below. |
| **3. Acknowledgment** | $T_2 = 13:33:15$<br>($T_1 + 75\text{s}$) | User taps kiosk or phone notification. | Hardware unaffected. | Engine calls Pushover API to cancel receipt `r7k9m2x4v1`. Dispatches silent broadcast to all staff: *"🔕 Acknowledged by Dr. Ostrom. Staff attending."* | **`alarm_events`:** **ROW 33 UPDATED** with `is_acknowledged = TRUE`, `acknowledged_by = 'Dr. Ostrom'`, `acknowledged_at = NOW()`.<br>See [SQL Update](#sql-update-at-acknowledgment) below. |
| **4. Door Closed & Cooling** | $T_3 = 13:35:00$<br>($T_1 + 3\text{m}$) | User closes fridge door; compressor cools chamber. | Ch 112 drops: $9.8^\circ\text{C} \rightarrow 8.9^\circ\text{C} \rightarrow 7.6^\circ\text{C}$. Ch 123 remains 1 while $>8.0^\circ\text{C}$. | Kiosk banner remains steady green: `🟢 ACKNOWLEDGED: In-Lab Staff Attending`. | **`mincopy_historical`:** Records 1-minute historical trace showing cooling rate.<br>**`alarm_events`:** No change (still active, acknowledged). |
| **5. Resolution & Restabilization** | $T_4 = 13:38:00$<br>($T_1 + 6\text{m}$) | Temp drops below $+8.0^\circ\text{C}$ (reaches $+7.5^\circ\text{C}$). | PLC timer resets: `fbFridgeAlarm.bAlarm` $\rightarrow$ `FALSE`. Ch 123 $\rightarrow$ 0. | Engine detects Ch 123 drop. Sends Priority 0 chime: *"🟢 RESOLVED: Medical Refrigerator Normal (7.5°C). Duration: 6m 0s."* Kiosk banner dismisses. | **`alarm_events`:** **ROW 33 FINALIZED** with `is_resolved = TRUE`, `resolved_at = NOW()`, `duration_seconds = 360`.<br>See [SQL Update](#sql-update-at-resolution) below. |

---

### Exact SQL Statements Executed During the Event

#### <a id="sql-insert-at-trip"></a>A. At Trip ($T_1 = 13:32:00$):
Executed by [trigger_alarm()](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py#L276-L281):
```sql
INSERT INTO mod_arc_postgre_sql.alarm_events 
    (cnl_num, equipment_name, alarm_type, excursion_val, triggered_at, pushover_receipt, is_acknowledged, is_resolved, priority)
VALUES 
    (123, 'Medical Refrigerator', 'High Temperature Excursion', 9.8, '2026-10-24 13:32:00-08', 'r7k9m2x4v1', FALSE, FALSE, 2)
RETURNING id;
```

#### <a id="sql-update-at-acknowledgment"></a>B. At Acknowledgment ($T_2 = 13:33:15$):
Executed by [acknowledge_alarm()](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py#L380-L387):
```sql
UPDATE mod_arc_postgre_sql.alarm_events 
SET is_acknowledged = TRUE, 
    acknowledged_by = 'Dr. Ostrom', 
    acknowledged_by_token = 'user_phone_token_xyz', 
    acknowledged_at = '2026-10-24 13:33:15-08' 
WHERE id = 33;
```

#### <a id="sql-update-at-resolution"></a>C. At Resolution ($T_4 = 13:38:00$):
Executed by [resolve_alarm()](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py#L324-L330):
```sql
UPDATE mod_arc_postgre_sql.alarm_events 
SET is_resolved = TRUE, 
    resolved_at = '2026-10-24 13:38:00-08', 
    duration_seconds = 360
WHERE id = 33;
```

---

## 6. Regulatory Compliance Auditing & Inspector Queries

When laboratory accreditation bodies (CAP, CLIA, Joint Commission) inspect the facility, inspectors ask for proof of:
1. Equipment temperature stability.
2. Timely response and human intervention during an out-of-range event.
3. Total elapsed time before the chamber returned to safe operating parameters.

### Audit Inspection Query: Excursion Event Log
```sql
SELECT 
    id AS "Event ID",
    to_char(triggered_at, 'YYYY-MM-DD HH24:MI:SS') AS "Triggered Time",
    equipment_name AS "Equipment",
    excursion_val || ' °C' AS "Peak Excursion",
    acknowledged_by AS "Acknowledged By",
    to_char(acknowledged_at, 'HH24:MI:SS') AS "Ack Time",
    ROUND(EXTRACT(EPOCH FROM (acknowledged_at - triggered_at))) || 's' AS "Response Lag",
    to_char(resolved_at, 'HH24:MI:SS') AS "Restabilized Time",
    (duration_seconds / 60) || 'm ' || (duration_seconds % 60) || 's' AS "Total Duration"
FROM mod_arc_postgre_sql.alarm_events
WHERE triggered_at >= NOW() - INTERVAL '30 days'
ORDER BY triggered_at DESC;
```

#### Audit Output Sample:
| Event ID | Triggered Time | Equipment | Peak Excursion | Acknowledged By | Ack Time | Response Lag | Restabilized Time | Total Duration |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **33** | 2026-10-24 13:32:00 | Medical Refrigerator | 9.8 °C | Dr. Ostrom | 13:33:15 | 75s | 13:38:00 | 6m 0s |
| **32** | 2026-10-24 09:14:10 | Incubator 01 | 35.6 °C | Lab Kiosk | 09:14:52 | 42s | 09:21:05 | 6m 55s |

### Cross-Validation Query: Raw Historical Time-Series Trace
To verify the exact cooling curve during an excursion, inspectors correlate the event ID with raw historical intervals in `mincopy_historical`:
```sql
SELECT 
    to_char(d_time, 'YYYY-MM-DD HH24:MI:SS') AS "Timestamp",
    val AS "Temp (°C)",
    stat AS "Status"
FROM mod_arc_postgre_sql.mincopy_historical
WHERE cnl_num = 112 
  AND d_time BETWEEN '2026-10-24 13:28:00' AND '2026-10-24 13:42:00'
ORDER BY d_time ASC;
```

---

## 7. Related System Architecture Documents

* **Cleanroom Touchscreen Kiosk UX Specification:** [cleanroom_touchscreen_kiosk_design.md](file:///home/bobostrom/Projects/labSCADA/notes/cleanroom_touchscreen_kiosk_design.md) — Covers the physical touchscreen kiosk, 2-tab navigation (`/` and `/cryo`), 6-card dashboard layout, glove-friendly tap targets, and daily CAP verification banner.
* **Liquid Nitrogen Compliance & Dipstick Architecture:** [ln2_tank_manual_dipstick_and_compliance_architecture.md](file:///home/bobostrom/Projects/labSCADA/notes/ln2_tank_manual_dipstick_and_compliance_architecture.md) — Covers dual cryo tank dipstick audit protocols, sawtooth evaporative modeling, and automated report generation.
* **Alert Engine Implementation:** [ivf_alert_engine.py](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py) — The Python service handling telemetry scanning, Pushover dispatch/cancellation, and web kiosk hosting on port 8080.
* **PLC Source Code:** [codesys/src/PLC_PRG.st](file:///home/bobostrom/Projects/labSCADA/codesys/src/PLC_PRG.st) — CODESYS IEC 61131-3 logic managing `tPickupDelay` filters and discrete alarm bits.

# IVF Clinical Alarm Management & Touchscreen Kiosk Architecture

## 1. Executive Summary & Clinical Context
In an IVF and embryology cleanroom suite, operational realities dictate strict protocols for sterile handling and equipment interaction:
* **Sterile Field Constraints:** Technicians and embryologists work gloved while manipulating delicate gametes and embryos under laminar flow hoods. They cannot and should not deglove, retrieve contaminated personal mobile devices, and navigate apps to silence alarms during active procedures.
* **Expected vs. Unexpected Thermal Dips:** Opening incubator doors or benchtop chambers for dish loading, media equilibration, or inspection naturally introduces transient ambient air mixing and temperature drops. These operational excursions are normal and expected.
* **Core Design Objectives:**
  1. **Nuisance Alarm Suppression:** Eliminate false off-site alarms caused by routine sterile workflows.
  2. **Glove-Friendly Touchscreen Acknowledgment:** Enable instant, one-tap silence directly on a wall-mounted lab kiosk.
  3. **Team Peace of Mind:** Instantly inform off-site on-call physicians/directors when an in-lab technician is actively attending to an issue.
  4. **Strict Regulatory Compliance:** Maintain a permanent, tamper-proof digital audit trail in PostgreSQL meeting CAP, CLIA, and FDA 21 CFR Part 11 requirements.

---

## 2. Nuisance Alarm Prevention (Smart SCADA & RTAC Logic)

To prevent sirens from waking up on-call staff during routine laboratory hours, the SEL RTAC and Rapid SCADA system leverage multi-variable correlation:

```
                  ┌────────────────────────┐
                  │ Door Sensor Active?    │
                  │ (Cnl 121 / 122 = Open) │
                  └───────────┬────────────┘
                              │
               YES ───────────┴─────────── NO
                │                           │
  ┌─────────────▼─────────────┐ ┌───────────▼─────────────┐
  │ Start Recovery Holdoff    │ │ Evaluate Raw Excursion  │
  │ Timer (e.g. 5-8 min)      │ │ On-Delay Timer (>3 min) │
  └─────────────┬─────────────┘ └───────────┬─────────────┘
                │                           │
  Excursion within window?      Sustained excursion > limit?
        │             │               │              │
      YES             NO             YES             NO
       │               │              │               │
  [Suppress Siren] [Escalate]    [FIRE SIREN]   [Normal Draft]
```

### A. Door-Linked Recovery Holdoff
* **Sensors:** RTAC Discrete Inputs `DoorOpen_01` (Cnl 121) and `DoorOpen_02` (Cnl 122).
* **Behavior:** When an incubator door is opened, the SCADA logic registers the event. When the door closes, a **Thermal Recovery Holdoff Timer** (configurable between 5 to 8 minutes) begins.
* If temperatures dip during or immediately following door closure, emergency sirens to phones are suppressed while the chamber's heating element recovers.
* **Fail-Safe:** If the chamber fails to recover to nominal temperature after the holdoff timer expires, the event immediately escalates to a full Priority 2 emergency alert.

### B. On-Delay Sustained Excursion Filter
* Transient ambient drafts (e.g., room door opening, HVAC cycling) can cause brief sensor fluctuations lasting under 60 seconds.
* An On-Delay timer requires an excursion to persist continuously for **> 180 seconds** before triggering an emergency alert.

### C. Touchscreen "Work Mode" (Manual Procedure Window)
* For scheduled intensive procedures (e.g., morning dish loading, oocyte retrieval batching):
* Technicians tap a dedicated **`[ Start 15-Min Chamber Work Mode ]`** button on the lab kiosk.
* **Action:** Suppresses remote sirens for the selected chamber during the procedure window. Temperatures continue logging silently to PostgreSQL without interruption.
* **Safety Lock:** Automatically expires and re-arms when the timer finishes, ensuring the chamber is never inadvertently left unprotected.

### D. Audit Trail Boundaries: Suppression of Transient Dips
* **Regulatory Design Decision:** Transient thermal dips that recover within the PLC pickup delay (e.g. routine door access < 2m on fridge, < 3m on freezer, < 30s on cryo tanks) are deliberately **suppressed from generating records in `mod_arc_postgre_sql.alarm_events`**.
* **Clinical Rationale:** Avoids alarm fatigue, extraneous paperwork, and audit log bloat from expected daily sterile procedures.
* **Audit Assurance:** Continuous 1-minute historical time-series data is retained in `mod_arc_postgre_sql.mincopy_historical` for 365 days, ensuring inspectors can always review raw temperature traces while keeping the clinical alarm log reserved for actionable emergencies.

---

## 3. Lab Kiosk UX & Glove-Friendly Touchscreen Workflow

The lab kiosk runs on a wall-mounted touch display running Grafana in Kiosk mode (`?kiosk`), providing visibility from across the room.

### Kiosk Display States

#### Normal State (All Clear)
* Calm dark theme with ambient green status indicators.
* Live chamber temperatures, gas levels, and security statuses prominently displayed.

#### Active Alarm State
* The top of the screen transitions to a high-contrast, flashing **Red/Amber Alert Banner**.
* Displays the specific chamber, excursion reading, and elapsed duration.
* Features an oversized touch target designed for gloved hands:

```text
╔═══════════════════════════════════════════════════════════════════════╗
║ 🔴 CRITICAL ALARM: Incubator 01 Temp Low (35.6°C) • Tripped 45s ago  ║
║                                                                       ║
║         ┌───────────────────────────────────────────────────┐         ║
║         │    ✋ TAP TO ACKNOWLEDGE & SILENCE SIREN          │         ║
║         └───────────────────────────────────────────────────┘         ║
╚═══════════════════════════════════════════════════════════════════════╝
```

### What Happens When Tapped:
1. **Instant Siren Cancellation:** The repeating emergency siren immediately halts for all team members.
2. **Visual Acknowledgment:** The kiosk banner turns to steady green:
   * *`🟢 ACKNOWLEDGED: In-Lab Staff Attending (09:14:22)`*
3. **On-Call Team Notification:** Pushover sends a silent informational message to off-site physicians and directors:
   * *`ℹ️ Incubator 01 low temp acknowledged by Lab Kiosk staff. Situation attended.`*
4. **Database Stamping:** The event is updated in PostgreSQL with timestamp and acknowledgement source.

---

## 4. Clean Pushover Receipt Architecture (No Generic Tags)

Rather than using generic tags (`tags=ivf_alarm`) which risk blanket-silencing unrelated emergencies, the architecture tracks discrete, per-alarm **`receipt` IDs**:

```
[Alarm Detected] ──► POST /1/messages.json (Priority=2)
                            │
                            ▼ Returns { "receipt": "r9a8b7c6d5" }
                     ┌──────────────────────────────────┐
                     │ Save to PostgreSQL `alarm_events`│
                     └──────────────┬───────────────────┘
                                    │
               ┌────────────────────┴────────────────────┐
               │                                         │
        [Kiosk Tap Ack]                       [Phone Screen Ack]
               │                                         │
               ▼                                         ▼
   POST /1/receipts/cancel/r9a8b...             Pushover records
   (Cancels this specific siren)                acknowledged_by user
               │                                         │
               └────────────────────┬────────────────────┘
                                    │
                                    ▼
                      UPDATE PostgreSQL `alarm_events`
                      - is_acknowledged = true
                      - acknowledged_by = user
                      - acknowledged_at = timestamp
```

### Advantages of Receipt Tracking:
* **Isolation:** Silencing an incubator door alarm will **never** silence a separate cryo tank or second incubator alert.
* **Accountability:** Captures the identity of the specific responder, whether acknowledged from an iPhone lock screen, Android notification, or the lab kiosk.

---

## 5. PostgreSQL Schema & Regulatory Audit Trail

To satisfy CAP (College of American Pathologists), CLIA, and Joint Commission audit criteria, all events are stored permanently in the `rapid_scada` database.

### Proposed Table: `mod_arc_postgre_sql.alarm_events`
```sql
CREATE TABLE mod_arc_postgre_sql.alarm_events (
    id SERIAL PRIMARY KEY,
    cnl_num INTEGER NOT NULL,
    equipment_name VARCHAR(64) NOT NULL,
    alarm_type VARCHAR(64) NOT NULL,
    excursion_val DOUBLE PRECISION,
    triggered_at TIMESTAMPTZ NOT NULL,
    pushover_receipt VARCHAR(64),
    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(64),
    acknowledged_at TIMESTAMPTZ,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    corrective_action_notes TEXT
);
```

### Compliance Reporting Output:
Inspectors frequently review thermal excursion logs. With this data structure, a single query generates an audit-ready report:

| Date / Time | Equipment | Excursion Reading | Notification Sent | Acknowledged By | Response Time | Chamber Restabilized |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-10-14 09:14:10 | Incubator 01 | 35.6°C (Low) | Pushover Siren | Lab Kiosk | 42 seconds | 2026-10-14 09:21:05 (6m 55s) |
| 2026-10-14 14:02:18 | Door 02 (Cryo) | Open > 3 min | Pushover Alert | Dr. Ostrom (Phone) | 1m 15s | 2026-10-14 14:05:40 (3m 22s) |

---

## 6. Implementation Stages

| Phase | Milestone | Deliverable |
| :--- | :--- | :--- |
| **Phase 1** | **SCADA Holdoff Logic** | Configure RTAC & Rapid SCADA channel logic to correlate door contacts (`Cnl 121/122`) with temperature alarm triggers. |
| **Phase 2** | **Receipt-Tracking DB Table** | Initialize `alarm_events` table in PostgreSQL with auto-inherited `grafana_reader` permissions. |
| **Phase 3** | **Kiosk UI Panel** | Add interactive Alarm Banner & glove-friendly Acknowledge button to the Grafana dashboard. |
| **Phase 4** | **Two-Way Pushover Sync** | Connect Pushover receipt cancellation and phone-ack webhook into PostgreSQL for bidirectional status tracking. |

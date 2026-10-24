# Cleanroom Touchscreen Kiosk UX & Operation Design

## 1. Cleanroom Ergonomics & Hardware Strategy

In an Assisted Reproductive Technology (ART) and embryology cleanroom suite, user interaction with software occurs in a sterile, high-stakes environment:

* **Sterile Field Constraints:** Technicians and embryologists wear sterile nitrile or latex gloves. They work under laminar flow hoods and manipulators. Degloving, navigating multi-level menus, typing on mechanical keyboards, or using small mobile phones in the cleanroom is strictly forbidden by standard operating procedures.
* **Visibility from a Distance:** The kiosk display must be readable from 10 to 15 feet away across the cleanroom suite, providing immediate situational awareness to embryologists without requiring them to walk away from their microscopes.
* **Hardware Profile:** A wall-mounted, high-contrast, glove-friendly touch panel (running full-screen kiosk browser mode without browser address bars or navigation buttons).
* **Core Interaction Rules:**
  1. **Oversized Touch Targets:** All interactive elements (buttons, acknowledgment banners, tab selectors) feature generous tap targets ($\ge 60\text{px}$ height) easily activated by gloved fingertips.
  2. **Flat Information Architecture:** No deep menu trees or nested modals. Every critical operation is accessible within a maximum of one tap.
  3. **High-Contrast Ambient Feedback:** Color-coded status cues (emerald green for nominal, amber for debounce countdowns, crimson for active excursions) ensure zero ambiguity.
  4. **Fast, Lightweight Performance:** Zero external CDN dependencies, minimal footprint, and instant client-side tab switching.

---

## 2. System Architecture & Web Delivery

The Cleanroom Kiosk web application is served directly by the [ivf_alert_engine.py](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py) service running locally on `SCADAPi02` at port 8080:

* **Primary Endpoint:** `http://192.168.10.133:8080/`
* **Technology Stack:**
  * **Backend:** Native Python HTTP daemon running multi-threaded request workers and background telemetry scanners.
  * **Frontend:** Vanilla HTML5, CSS3 Grid/Flexbox design system, and client-side JavaScript.
  * **Telemetry Polling:** Asynchronous 1.0-second JSON polling via `/api/telemetry`, fetching live values, alarm states, and CAP verification status directly from PostgreSQL.
  * **Client-Side Routing:** HTML5 `history.pushState` navigation supporting deep linking and instant switching between `/` and `/cryo` without page reloads.

---

## 3. Two-Tab Information Architecture

To maintain clarity and prevent visual overload, the kiosk interface is partitioned into two specialized views accessible via top-level glove-friendly tabs:

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│  🧪 IVF LAB MONITORING SYSTEM                     [ 🖥️ Live Operations ]  [ ❄️ Cryo Suite ]│
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   Tab 1: Live Operations (`/`)                   Tab 2: Cryo Tank Audit Suite (`/cryo`)  │
│   • Daily CAP/CLIA Verification Banner           • Cryo Tank 1 Level & Evaporation      │
│   • 6 Consolidated Cleanroom Cards               • Cryo Tank 2 Level & Evaporation      │
│   • Flashing Excursion Banner & Siren Silence    • 30-Day Sawtooth Evaporation Chart    │
│   • Recent Alarm Audit Trail Table               • Manual Dipstick Logging Modal        │
│                                                  • 1-Click CAP Compliance PDF Reports   │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

Both tabs remain active in the DOM simultaneously (`display: block` vs `display: none`), eliminating network round-trips and rendering instantly upon touch.

---

## 4. Live Operations Page Layout (6 Consolidated Cards)

The main operational screen (`/`) presents the cleanroom status in a responsive, balanced 6-card grid:

```
┌──────────────────────────────┬──────────────────────────────┬──────────────────────────────┐
│  ❄️ CRYO TANK 1 (EMBRYOS)     │  ❄️ CRYO TANK 2 (SPERM)       │  🧊 MEDICAL COLD STORAGE     │
│  -196.2 °C   🟢 NORMAL       │  -196.0 °C   🟢 NORMAL       │  Fridge: +4.2 °C  🟢 NORMAL  │
│  Level: 14.5 cm (Safe)       │  Level: 16.8 cm (Safe)       │  Freezer: -19.1°C 🟢 NORMAL  │
│  Dipstick: Today 08:30 (OK)  │  Dipstick: Today 08:35 (OK)  │  Threshold: +2..+8 / <-15°C  │
├──────────────────────────────┼──────────────────────────────┼──────────────────────────────┤
│  🌡️ CLEANROOM AMBIENT        │  🚪 CLEANROOM DOORS & ACCESS │  🔬 CHAMBER INCUBATORS       │
│  Temp: 21.4 °C  (20..24 °C)  │  Main Door: Closed 🟢        │  Incubator 01: 37.0 °C 🟢    │
│  Humidity: 45.2% RH          │  Cryo Door: Closed 🟢        │  Incubator 02: 37.0 °C 🟢    │
│  Diff Pressure: +22 Pa (Pos) │  Timer: Filter > 3m          │  CO2: 6.0%  |  O2: 5.0%      │
└──────────────────────────────┴──────────────────────────────┴──────────────────────────────┘
```

### Card Architecture & Logic

1. **Cryo Tank 1 (Embryos):** Monitored on Channels 125/113 (Temp) and 199 (Level). Displays live temperature, vapor level, the timestamp of the last manual dipstick verification, and a green `🟢 ON SCHEDULE` badge.
2. **Cryo Tank 2 (Sperm):** Monitored on Channels 104/114 (Temp) and 198 (Level). Mirrors Tank 1 with independent sensor validation and compliance verification.
3. **Medical Cold Storage (Consolidated Card):** Combines the Medical Refrigerator (Ch 112) and Medical Freezer (Ch 111) into a single cohesive card. Displays separate live readouts and status badges for both chambers.
4. **Cleanroom Ambient:** Tracks laboratory environmental parameters ensuring strict compliance with cleanroom ventilation, positive differential pressure, and humidity standards.
5. **Cleanroom Doors & Access (Consolidated Card):** Integrates Main Cleanroom Door (Ch 121) and Cryo Lab Door (Ch 122). Shows live contact status and suppresses door sirens until the PLC 3-minute on-delay timer expires.
6. **Chamber Incubators:** Live temperature, CO2, and O2 readouts for embryo culture chambers.

---

## 5. Alarm States & Touchscreen Interaction Ergonomics

The kiosk interface dynamically adapts across four distinct operational states:

### A. Nominal State (All Clear)
* Deep slate background (`#0a0e17`) with subdued dark card surfaces (`#111827`).
* Ambient emerald green indicators (`#10b981`) convey system health without visual fatigue.

### B. Pending Debounce State (Amber Warning)
* When a door opens or temperature crosses a threshold, the WAGO PLC pickup timer begins counting down ($0 \rightarrow 2\text{m}$ for fridge, $0 \rightarrow 3\text{m}$ for freezer/doors).
* The corresponding card badge turns amber: `🟡 DELAY (2M)` or `🟡 DELAY (3M)`.
* **Clinical Purpose:** Informs laboratory staff that the chamber is in an expected recovery or transit window without sounding emergency alarms.

### C. Active Excursion State (Flashing Red Banner)
* When the PLC on-delay timer expires, the discrete alarm bit trips.
* A high-contrast, flashing crimson banner deploys across the top of the kiosk:

```text
╔═══════════════════════════════════════════════════════════════════════════════════════╗
║ 🔴 CRITICAL ALARM: Medical Refrigerator Excursion (+9.8 °C) • Tripped 45s ago        ║
║                                                                                       ║
║         ┌───────────────────────────────────────────────────────────────────┐         ║
║         │            ✋ TAP TO ACKNOWLEDGE & SILENCE SIREN                  │         ║
║         └───────────────────────────────────────────────────────────────────┘         ║
╚═══════════════════════════════════════════════════════════════════════════════════════╝
```

* **Touch Target:** The button is sized for easy activation by a gloved palm or fingertip ($\ge 64\text{px}$ height, high-contrast border).

### D. Acknowledged State (In-Lab Staff Attending)
* When tapped, the repeating emergency sirens on off-site mobile devices immediately halt.
* The kiosk banner turns steady green:
  * `🟢 ACKNOWLEDGED: In-Lab Staff Attending (13:33:15)`
* A silent broadcast notification is dispatched to all off-site team members:
  * *"🔕 ALARM ACKNOWLEDGED: Medical Refrigerator acknowledged by Lab Kiosk staff at 13:33:15. Siren silenced. Staff attending."*
* The banner remains until the physical temperature restabilizes and the alarm bit drops, at which point the banner dismisses automatically.

---

## 6. Daily Alarm Pathway Verification Banner (CAP / CLIA)

CAP Reproductive Laboratory accreditation mandates daily verification of the emergency alarm notification pathway.

A dedicated verification panel is positioned at the top of the Live Operations view:

```text
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ 🛡️ DAILY ALARM PATHWAY VERIFICATION (CAP/CLIA)                    🟢 VERIFIED TODAY   │
│ Last Verified: 2026-10-24 08:15:22 by Lab Kiosk                   [ Run Daily Test ]  │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### Verification Workflow:
1. Every morning, the banner displays `🟡 PENDING TODAY`.
2. A staff member taps **`[ Run Daily Test ]`**.
3. The engine initiates an end-to-end pathway verification:
   * Dispatches a live test siren through Pushover with an active receipt.
   * Cancels the siren and logs receipt delivery confirmation.
   * Records a timestamped certification in `mod_arc_postgre_sql.alarm_events` (`equipment_name = 'QA System'`).
4. The banner instantly transitions to `🟢 VERIFIED TODAY` and displays the exact time and operator.

---

## 7. Cryo Tank Audit Suite Sub-Page (`/cryo`)

Tapping the **`❄️ Cryo Suite`** tab transitions to the cryogenic compliance environment:

1. **Current Physical Levels:** Liquid nitrogen depth (cm) compared against the critical minimum safe threshold ($10.0\text{ cm}$).
2. **Sawtooth Evaporation Modeling:** A dynamic chart plotting the 30-day liquid nitrogen consumption curve, illustrating fill cycles, daily boil-off rates (cm/day), and projected refill dates.
3. **Manual Dipstick Logging Modal:**
   * Staff tap **`[ Log Manual Dipstick ]`**.
   * An oversized numeric keypad modal allows quick entry of ruler readings (e.g., $14.5\text{ cm}$).
   * Cross-checks manual measurement against the electronic sensor, flagging discrepancies $> 2.0\text{ cm}$.
   * Writes the audit record to `mod_arc_postgre_sql.ln2_tank_logs`.
4. **1-Click Compliance Report Export:**
   * Buttons to generate and print standalone HTML/PDF compliance reports for **Cryo Tank 1** (`/report/ln2?tank=1`) and **Cryo Tank 2** (`/report/ln2?tank=2`).
5. **Printable Mobile QR Code Placards (`/print/qr`):**
   * Staff tap **`[ 📱 Print Tank QR Placards ]`** in the subpage header to generate print-ready laminated placards for the tanks outside the lab.
   * Enables non-lab staff, facilities, and clinical nurses to scan the QR code with their smartphone and submit measurements without gowning into the cleanroom suite.

---

## 8. Touchscreen "Work Mode" (Manual Procedure Holdoff)

For planned procedural access (e.g., morning dish loading, oocyte retrieval batching, incubator cleaning):

* Technicians tap **`[ Start 15-Min Procedure Work Mode ]`**.
* **Action:** Suppresses remote emergency sirens for the selected chamber during the procedure window.
* **Continuous Logging:** Raw temperature readings continue logging uninterrupted to `mod_arc_postgre_sql.mincopy_historical`.
* **Automatic Re-Arm:** An on-screen countdown timer displays the remaining time. When the timer reaches zero, the system automatically re-arms normal alarm monitoring, ensuring equipment is never inadvertently left unprotected.

---

## 9. Related User Manual Sections

* **Clinical Alarm Architecture & Regulatory Lifecycle:** [02_clinical_alarm_response_and_regulatory_lifecycle.md](file:///home/bobostrom/Projects/labSCADA/user_manual/02_clinical_alarm_response_and_regulatory_lifecycle.md) — Detailed regulatory rationale (CAP/CLIA), PLC debouncing algorithms, Pushover receipt architecture, PostgreSQL schema, and complete operational walkthroughs.
* **Liquid Nitrogen Compliance & Dipstick Architecture:** [03_liquid_nitrogen_tank_dipstick_and_compliance.md](file:///home/bobostrom/Projects/labSCADA/user_manual/03_liquid_nitrogen_tank_dipstick_and_compliance.md) — Detailed dual cryo tank dipstick protocols, manual measurement validation, and report generation.
* **Alert Engine & Kiosk Server Implementation:** [ivf_alert_engine.py](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py) — The Python service providing the web application and telemetry API on port 8080.

# Medical Freezer Excursion Review, Thermal Buffer Filter & Monitoring Plan

| Document Field | Record Detail |
|---|---|
| **Document ID / Record Type** | `QA-EXCURSION-2026-11-15` • Equipment Excursion Review & QA Monitoring Sign-Off |
| **Facility** | Advanced Fertility of Alaska (AFOA) |
| **Report Date** | November 15, 2026 |
| **Monitored Equipment** | Cold Storage Combo Unit — Medical Freezer & Medical Fridge<sup>*</sup> |
| **Freezer Scope / Intended Use** | **Medical Supplies & Cold Packs Only** *(Non-biological storage; no specimens, gametes, embryos, or certified biological samples are stored in this freezer)* |
| **Referenced Alarm IDs** | Medical Freezer `#419` (Nov 14, `18:15:45 – 18:34:31`) & `#432` (Nov 15, `21:32:27 – 21:49:33`); Medical Fridge (no excursion) |
| **Interim Disposition** | Pending 3–5 Day Baseline Data Collection (No Setting Change Yet • Target Re-Review: Nov 18–20, 2026) |

---

## 1. Executive Summary

- **Which unit alarmed:** The active alarms on Nov 14 (`#419`) and Nov 15 (`#432`) were both on the **Medical Freezer** (used strictly for **medical supplies**), not the **Medical Fridge**. Over the monitoring window, the Medical Fridge stayed inside its `1.0°C – 10.0°C` operating limits (`5.71°C – 8.84°C`, Nov 15 median `7.03°C`).
- **Real event vs. sensor glitch:** System diagnostics confirm the readings are **physically real**, not a faulty probe, swapped sensor, or wireless dropout. Both excursions match a **periodic frost-free automatic defrost cycle** (~17–19 minutes above `0.0°C`, repeating ~27 hours apart), and both recovered automatically once cooling resumed.
- **Recommendation:** **Let the system run unchanged for 3–5 more days** to collect additional defrost cycles and daytime data before adjusting any filter or alarm settings. Once we have a multi-day baseline—and confirm how the freezer probe is mounted next to stored medical supplies—we can choose the safest combination of physical buffering or software filter tuning.

---

## 2. Observed Readings & Event Summary

### Sensor & Communication Health Check<sup>**</sup>
During tonight's excursion (`Nov 15 21:32 – 21:49`), monitoring diagnostics showed normal operation across all sensors:

- **Probe health:** All 3 probes (Fridge, Freezer, Room Ambient) reported valid readings — no probe faults and no sensor-slot mix-ups
- **Wireless link:** Good communications (fresh readings arriving every `15–21 s`, strong wireless signal, healthy `3.91 V` battery)
- **Room / door activity:** Last cleanroom door activity ended at `20:33:18` (~1 hour before the excursion)

### Freezer Baseline & Defrost Cycles (`Nov 14 18:00 – Nov 15 21:50`, 27.83 hours)
Historical 1-minute data (`1,671` samples) shows two recurring behaviors in the freezer compartment:

1. **Normal ~2h 15m cooling cycle:**  
   The freezer cools down to **`-20°C` to `-21.6°C`**, drifts up to **`-4.2°C to -4.6°C`** between compressor runs, and cycles back down. The 24-hour median temperature on Nov 15 was **`-12.18°C`**.

2. **Active auto-defrost cycle (~27 hours apart):**

| Event | Alarm ID | Crossed `0.0°C` | Recovered `< -0.5°C` | Duration | Peak Modeled Temp | Peak Raw Air Temp | Lab Room Shift |
|---|---|---:|---:|---:|---:|---:|---|
| **Nov 14 Defrost** | `#419` | `18:15:45` | `18:34:31` | `18m 46s` | **`+7.74°C`** | ~`+15.0°C` *(est.)* | `22.1°C → 24.0°C` |
| **Nov 15 Defrost** | `#432` | `21:32:27` | `21:49:33` | `17m 06s` | **`+6.35°C`** | **`+8.1°C`** *(live air probe)* | `22.2°C → 23.3°C` |

Both curves rose smoothly over ~24 minutes from `-15°C / -21.6°C` to above `+6°C`, followed by a small `~1–2°C` rise in room temperature as defrost heat dissipated, then cooled rapidly back below freezing as soon as the compressor restarted (`-1.21°C` by `21:50`).

---

## 3. How the Thermal Filter ("Virtual Buffer Vial") Works

An exposed temperature probe responds quickly to fast-moving air currents (such as an evaporator defrost cycle or brief door opening), whereas medical supplies, cold packs, and buffered containers change temperature much more slowly due to their **thermal mass**.

To mimic placing the sensor inside a physical buffer bottle (such as glycol, mineral oil, or glass beads), the monitoring controller applies a **first-order thermal lag filter** (an Exponentially Weighted Moving Average, or EWMA) to the incoming air temperature readings.<sup>***</sup>

### Continuous Physical Model
Heat transfer between the surrounding freezer air and a buffered vial follows Newton's law of heating and cooling:

$$\tau \frac{dT_{\text{vial}}}{dt} = T_{\text{air}}(t) - T_{\text{vial}}(t)$$

Where:

- $T_{\text{air}}(t)$ = instantaneous air temperature measured by the freezer probe
- $T_{\text{vial}}(t)$ = modeled temperature inside the buffer vial (logged to the monitor and used for alarms)
- $\tau$ = **thermal time constant** (minutes), representing the thermal inertia of the vial

For a sudden air temperature change from $T_0$ to $T_{\text{air}}$, the buffered temperature approaches the new air temperature exponentially:

$$T_{\text{vial}}(t) = T_{\text{air}} + (T_0 - T_{\text{air}}) \, e^{-t / \tau}$$

In practical terms:

- After **$1 \times \tau$**, the buffered reading has moved **63.2%** of the way toward the new air temperature.
- After **$2 \times \tau$**, it has moved **86.5%**.
- After **$3 \times \tau$**, it has moved **95.0%**.

Short heat pulses much briefer than $\tau$ are strongly dampened, whereas sustained warming (e.g., an unplugged unit or failed compressor) still drives $T_{\text{vial}}$ cleanly across the alarm threshold.

### Step-by-Step Controller Update
Every fixed 5-second interval ($\Delta t = 5\text{ s}$), the controller nudges the modeled vial temperature slightly toward the latest air reading:

$$\alpha = \frac{\Delta t}{\tau + \Delta t}$$

$$T_{\text{vial}}[k] = T_{\text{vial}}[k-1] + \alpha \Big(T_{\text{air}}[k] - T_{\text{vial}}[k-1]\Big)$$

*(In plain terms: every 5 seconds, the smoothed reading moves by the fraction $\alpha$ toward the current air temperature.)*

### Current Freezer Settings
- **Update interval ($\Delta t$):** `5 seconds`
- **Thermal time constant ($\tau$):** `8 minutes` (`480 seconds`)  
  → Step weight per update: $\alpha = \frac{5}{480 + 5} \approx 0.01031$ (`~1.03%` toward air temperature every 5 seconds)
- **High alarm threshold:** `0.0°C`
- **Recovery margin:** `0.5°C` (alarm clears once filtered temperature drops below `-0.5°C`)
- *(For comparison, the Medical Fridge uses $\tau = 5\text{ minutes}$ with `1.0°C – 10.0°C` limits.)*

### Why the `8 min` Filter Still Triggered During Defrost
Each defrost warming period lasted roughly **24–30 minutes** (`~3×` the `8-minute` time constant). Because $3\tau$ allows ~95% tracking of a temperature change, the `8-minute` virtual vial followed the defrost heat spike well past `0.0°C` (`+7.74°C` on Nov 14 and `+6.35°C` on Nov 15).

---

## 4. Replay of Longer Filter Settings on Existing Data

Replaying the reconstructed raw air trace from our `27.83-hour` clean window (`Nov 14 18:00 – Nov 15 21:50`, covering both defrost cycles) through different buffer time constants gives the following simulated behavior:

| Buffer Time Constant ($\tau$) | Step Weight $\alpha$ (per 5s) | Max Simulated Peak (Both Defrosts) | Total Minutes `> 0.0°C` | Total Minutes `> -5.0°C` |
|---:|---:|---:|---:|---:|
| **`8 min`** *(current)* | `0.01031` | **`+8.08°C`** | `36 min` | `135 min` |
| `15 min` | `0.00552` | `+3.36°C` | `24 min` | `71 min` |
| `20 min` | `0.00415` | `+0.67°C` | `5 min` | `36 min` |
| **`30 min`** | `0.00277` | **`-3.23°C`** | `0 min` | `18 min` |
| **`45 min`** | `0.00185` | **`-6.77°C`** | `0 min` | `0 min` |
| `60 min` | `0.00139` | `-8.12°C` | `0 min` | `0 min` |

### Important Tradeoff to Keep in Mind
Increasing $\tau$ (for example, to `30–45 minutes`) would keep the filtered temperature below `0.0°C` during a ~20-minute defrost spike—**but a software filter cannot distinguish a defrost cycle from a real failure** (such as an unplugged power cord or propped-open door). A larger $\tau$ delays alarm notification during a genuine outage by a comparable time window, and the virtual time constant should reasonably reflect the thermal inertia of the actual supplies stored inside.

---

## 5. Why Letting It Run a Few More Days Is Recommended

With sensor-slot tracking just stabilized on Nov 14, we currently have **only 2 clean defrost cycles (~28 hours of data)**. Allowing the system to run unchanged for **3–5 additional days** gives us important operational evidence before changing anything:

1. **Establish defrost repeatability & worst-case variance:** Confirm how consistently defrost cycles occur (timing, duration, and peak air temperature) across normal weekday use when doors are opened during the day.
2. **Verify probe buffering & placement:** Confirm whether the freezer probe is sitting in bare air (or near the evaporator/defrost airflow) vs. inside a physical thermal buffer bottle/block next to stored supplies, and verify whether buffered material temperatures stay safely frozen during defrost.
3. **Verify intended-use & alarm threshold alignment:**

    - Because normal compressor off-cycles already reach **`-4.2°C to -4.6°C`** every ~2 hours and defrost air reaches **`+7°C to +8°C+`**, confirm that compartment use remains strictly limited to non-biological medical supplies and cold packs tolerant of brief defrost cycling (with biological samples/specimens excluded from this unit).
    - *(Secondary observation for review: on Nov 14, failed calibration verification checks on the Medical Fridge recorded `4.6°C` on the reference thermometer vs. `6.29–6.40°C` on the monitor, with no calibration offset currently applied.<sup>****</sup>)*

### Suggested Action After 3–5 Days of Data
Once we have 5–7 days of continuous logs, we can review the multi-day defrost curves together and decide cleanly between:

- Adding a **physical thermal buffer bottle/block** for the freezer probe (and keeping a modest $\tau$ matching supply thermal mass),
- Increasing the **software buffer time constant** (e.g., to `30–45 min`) if a `0.0°C` threshold is strictly intended to detect sustained refrigeration failure rather than brief auto-defrost air warmth, or
- Ensuring any temperature-critical biological materials or specialty reagents remain outside this auto-defrost medical supply freezer.

---

## 6. Supply Impact Assessment, Probe Check & QA Sign-Off

### Stored Medical Supplies & Physical Verification
- [ ] **Non-biological intended use confirmed:** This Medical Freezer stores **medical supplies only** (no biological samples, specimens, gametes, or embryos), and those supplies are compatible with periodic auto-defrost cycling (`-21.6°C` to `-4.2°C` baseline; brief `~17–19 min` air spikes above `0°C`).
- [ ] **Physical integrity check:** Visual inspection confirms stored medical supplies remain frozen/intact with no thaw or packaging concerns.  
  *Inspected supplies / notes:* `_________________________________________________________________________`
- [ ] **Freezer probe placement verified:**  
  [ ] Inside thermal buffer bottle/block &nbsp;&nbsp; [ ] In bare air / near evaporator vent &nbsp;&nbsp; [ ] Relocated *(loc: `_______________`)*
- [ ] **Alarm log & Fridge check reviewed:** Confirmed Alarms `#419` and `#432` auto-resolved below `-0.5°C`; noted Nov 14 Medical Fridge calibration check (`4.6°C` reference vs. `6.29–6.40°C` monitor, `0.0°C` offset applied) for follow-up.

### Interim Monitoring Disposition
- [ ] **Approved — Continue Current Settings (`8-minute` buffer filter):** Collect 3–5 additional days of baseline telemetry and re-review by **`Nov 18–20, 2026`**.
- [ ] **Immediate Mitigation Taken:** Relocated heat-sensitive supplies / requested immediate filter parameter adjustment.

### Follow-Up Action Log

| Action Item | Owner | Target Date | Completed (Date / Initials) |
|---|---|---|---|
| Verify freezer probe mounting & physical thermal buffering | | | |
| Re-verify Medical Fridge calibration & monitor offset | | | |
| Review 5–7 day defrost trend & finalize filter / buffering plan | | | |

### QA Approval & Signatures

| Role | Printed Name & Title | Signature | Date |
|---|---|---|---|
| **Technical Review / Prepared By** | | | |
| **Embryology / Lab Review Sign-Off** | | | |
| **Lab Director Approval** *(per SOP)* | | | |

### Post-Baseline Final Closure (Day 5–7 Re-Review)
- **Final Action:** &nbsp;[ ] Kept `8-min` filter &nbsp;&nbsp; [ ] Added physical thermal buffer &nbsp;&nbsp; [ ] Adjusted filter constant to `____ min` &nbsp;&nbsp; [ ] Relocated heat-sensitive supplies
- **Reviewer Initials & Date:** `______________ / ___________`
- **Closure Notes:** `____________________________________________________________________________`

---

### Engineering & System Reference Notes *(For Technical Audit Lookup)*
- **<sup>*</sup> Monitored hardware & SCADA channels:** Cold storage wireless node `cold_storage_node_01` mapped to PLC function block `fbColdStorage`; Medical Freezer temperature `cnl 103` / alarm `cnl 112`; Medical Fridge temperature `cnl 102` / alarm `cnl 111`.
- **<sup>**</sup> Diagnostic flags verified during Nov 15 event:** `uiRawFaultCode = 0`, `bProbeFault = False` (Fridge, Freezer, Ambient), `bFreezerSwapSuspect = False`, `bCommLoss = False`, telemetry age `15–21 s`, signal `iRSSI = -52 dBm`, battery `3.91 V`; raw air peak `fbFreezer.rRawTemp = +8.1°C` observed via OPC UA.
- **<sup>***</sup> PLC filter implementation:** Function block `FB_ThermalVial` inside `FB_MedFreezer` (`tSampleTick = T#5S`, `tThermalTau = T#8M` for Freezer, `T#5M` inside `FB_MedFridge`, `rHighTrip = 0.0°C` synced from `equipment.json`, `rHysteresis = 0.5°C`), converting raw `rRawTemp` to modeled `rProcessTemp`.
- **<sup>****</sup> Calibration reference:** Active PLC offsets (`fbFridge.rCalOffset` and `fbFreezer.rCalOffset`) are `0.0°C`; Nov 14 calibration log entries `#1–4` failed tolerance against a `4.6°C` NIST reference.

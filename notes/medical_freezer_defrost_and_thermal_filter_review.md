# Medical Freezer Excursion Review, Virtual Buffer Filter & Monitoring Plan

**Facility:** Advanced Fertility of Alaska (AFOA)  
**Date:** November 15, 2026  
**System:** Cold Storage Wireless Node (`cold_storage_node_01` / `fbColdStorage`)  
**Equipment:** Medical Freezer (`cnl 103` temp, `cnl 112` alarm) & Medical Fridge (`cnl 102` temp, `cnl 111` alarm)

---

## 1. Executive Summary

- **Which unit alarmed:** The active alarms on Nov 14 (`#419`) and Nov 15 (`#432`) were both on the **Medical Freezer** (`cnl 103` / `112`), not the **Medical Fridge** (`cnl 102`). Over the monitoring window, the Medical Fridge stayed inside its `1.0°C – 10.0°C` operating limits (`5.71°C – 8.84°C`, Nov 15 median `7.03°C`).
- **Real event vs. sensor glitch:** Telemetry diagnostics confirm the readings are **physically real**, not a probe swap, wiring fault, or wireless dropout. Both excursions match a **periodic frost-free automatic defrost cycle** (~17–19 minutes above `0.0°C`, repeating ~27 hours apart), and both recovered automatically once refrigeration resumed.
- **Recommendation:** **Let the system run unchanged for 3–5 more days** to collect additional defrost cycles and daytime session data before adjusting any filter or alarm settings. Once we have a multi-day baseline—and confirm how the freezer probe is mounted and what items are stored in that compartment—we can choose the safest combination of physical buffering, software filter tuning, or storage adjustment.

---

## 2. Observed Telemetry & Event Summary

### Sensor & Communication Health Check (`fbColdStorage` Live Diagnostics)
During tonight's excursion (`Nov 15 21:32 – 21:49`), PLC and wireless telemetry showed normal operation across all channels:

- **Probe health:** `uiRawFaultCode = 0`, `bProbeFault = False` (all 3 probes: Fridge, Freezer, Ambient), `bFreezerSwapSuspect = False`
- **Wireless link:** `bCommLoss = False`, packet age `15–21 s`, signal strength `iRSSI = -52 dBm`, battery `3.91 V`
- **Room / door activity:** Last cleanroom door activity ended at `20:33:18` (~1 hour before the excursion)

### Freezer Baseline & Defrost Cycles (`Nov 14 18:00 – Nov 15 21:50`, 27.83 hours)
Historical 1-minute data (`1,671` samples) shows two recurring behaviors in the freezer compartment:

1. **Normal ~2h 15m compressor cycle:**  
   The freezer cools down to **`-20°C` to `-21.6°C`**, drifts up to **`-4.2°C to -4.6°C`** between compressor runs, and cycles back down. The 24-hour median temperature on Nov 15 was **`-12.18°C`**.

2. **Active auto-defrost cycle (~27 hours apart):**

| Event | Alarm ID | Crossed `0.0°C` | Recovered `< -0.5°C` | Duration | Peak Filtered Temp (`rProcessTemp`) | Peak Raw Air Temp (`rRawTemp`) | Lab Ambient Shift |
|---|---|---:|---:|---:|---:|---:|---|
| **Nov 14 Defrost** | `#419` | `18:15:45` | `18:34:31` | `18m 46s` | **`+7.74°C`** | ~`+15.0°C` *(est.)* | `22.1°C → 24.0°C` |
| **Nov 15 Defrost** | `#432` | `21:32:27` | `21:49:33` | `17m 06s` | **`+6.35°C`** | **`+8.1°C`** *(live OPC UA)* | `22.2°C → 23.3°C` |

Both curves rose smoothly over ~24 minutes from `-15°C / -21.6°C` to above `+6°C`, followed by a small `~1–2°C` rise in room ambient as defrost/condenser heat rejected into the room, then cooled rapidly back below freezing as soon as the compressor restarted (`-1.21°C` by `21:50`).

---

## 3. How the Thermal Filter ("Virtual Buffer Vial") Works

An exposed digital temperature sensor responds quickly to fast-moving air currents (such as an evaporator defrost cycle or brief door opening), whereas liquids, gels, and frozen specimen/reagent containers change temperature much more slowly due to their **thermal mass**.

To emulate a sensor submerged in a physical buffer vial (such as glycol, mineral oil, or glass beads), the PLC function block [`FB_ThermalVial`](../project-view/FB_ThermalVial.st) applies a **first-order thermal lag filter** (an Exponentially Weighted Moving Average, or EWMA) inside [`FB_MedFreezer`](../project-view/FB_MedFreezer.st).

### Continuous Physical Model
Thermal exchange between surrounding freezer air and a buffered vial follows Newton's law of heating/cooling:

$$\tau \frac{dT_{\text{vial}}}{dt} = T_{\text{air}}(t) - T_{\text{vial}}(t)$$

Where:

- $T_{\text{air}}(t)$ = instantaneous air temperature measured by the sensor (`rRawTemp`)
- $T_{\text{vial}}(t)$ = modeled temperature inside the buffer vial (`rProcessTemp`, logged to SCADA & alarms)
- $\tau$ (`tThermalTau`) = **thermal time constant** (minutes/seconds), set by the vial's mass and heat-transfer rate

For a sudden air temperature change from $T_0$ to $T_{\text{air}}$, the buffered temperature approaches the new air temperature exponentially:

$$T_{\text{vial}}(t) = T_{\text{air}} + (T_0 - T_{\text{air}}) \, e^{-t / \tau}$$

In practical terms:

- After **$1 \times \tau$**, the buffered reading has moved **63.2%** of the way toward the new air temperature.
- After **$2 \times \tau$**, it has moved **86.5%**.
- After **$3 \times \tau$**, it has moved **95.0%**.

Short heat pulses much briefer than $\tau$ are strongly dampened, whereas sustained warming (e.g., an unplugged unit or failed compressor) still drives $T_{\text{vial}}$ cleanly across the alarm threshold.

### Discrete PLC Implementation (`FB_ThermalVial`)
Every fixed sample interval $\Delta t = 5\text{ s}$ (`tSampleTick = T#5S`), the PLC updates the virtual vial temperature:

$$\alpha = \frac{\Delta t}{\tau + \Delta t}$$

$$T_{\text{vial}}[k] = T_{\text{vial}}[k-1] + \alpha \Big(T_{\text{air}}[k] - T_{\text{vial}}[k-1]\Big)$$

*(Plain-text equivalent: `alpha = dt / (tau + dt)` and `T_vial = T_vial + alpha * (T_air - T_vial)` every 5 seconds.)*

### Current Freezer Settings
- **Sample tick ($\Delta t$):** `5 seconds`
- **Thermal time constant ($\tau$):** `8 minutes` (`480 seconds`, `T#8M`)  
  → Smoothing weight $\alpha = \frac{5}{480 + 5} \approx 0.01031$ (`~1.03%` step toward air temperature every 5 seconds)
- **High alarm threshold (`rHighTrip`):** `0.0°C` (configured in `equipment.json`, synced to PLC)
- **Hysteresis (`rHysteresis`):** `0.5°C` (alarm clears once filtered temperature drops below `-0.5°C`)
- *(Note: Medical Fridge uses $\tau = 5\text{ minutes}$ with `1.0°C – 10.0°C` limits.)*

### Why the `8 min` Filter Still Triggered During Defrost
Each defrost warming period lasted roughly **24–30 minutes** (`~3×` the `8-minute` time constant). Because $3\tau$ allows ~95% tracking of a temperature shift, the `8-minute` virtual vial followed the air spike well past `0.0°C` (`+7.74°C` on Nov 14 and `+6.35°C` on Nov 15).

---

## 4. Replay of Longer Filter Constants on Existing Data

Replaying the reconstructed raw air trace from our `27.83-hour` clean window (`Nov 14 18:00 – Nov 15 21:50`, covering both defrost cycles) through different values of $\tau$ gives the following simulated behavior:

| `tThermalTau` ($\tau$) | Smoothing Weight $\alpha$ (per 5s) | Max Simulated Peak (Both Defrosts) | Total Minutes `> 0.0°C` | Total Minutes `> -5.0°C` |
|---:|---:|---:|---:|---:|
| **`8 min`** *(current)* | `0.01031` | **`+8.08°C`** | `36 min` | `135 min` |
| `15 min` | `0.00552` | `+3.36°C` | `24 min` | `71 min` |
| `20 min` | `0.00415` | `+0.67°C` | `5 min` | `36 min` |
| **`30 min`** | `0.00277` | **`-3.23°C`** | `0 min` | `18 min` |
| **`45 min`** | `0.00185` | **`-6.77°C`** | `0 min` | `0 min` |
| `60 min` | `0.00139` | `-8.12°C` | `0 min` | `0 min` |

### Important Tradeoff to Keep in Mind
Increasing $\tau$ (for example, to `30–45 minutes`) would keep the filtered temperature below `0.0°C` during a ~20-minute defrost spike—**but a software filter cannot distinguish a defrost cycle from a real failure** (such as an unplugged power cord or propped-open door). A larger $\tau$ delays alarm notification during a genuine outage by a comparable time window, and the virtual time constant should reasonably reflect the thermal inertia of the actual items stored inside.

---

## 5. Why Letting It Run a Few More Days Is Recommended

With probe ROM pinning just stabilized on Nov 14, we currently have **only 2 clean defrost cycles (~28 hours of data)**. Allowing the system to run unchanged for **3–5 additional days** gives us important clinical and operational evidence before changing anything:

1. **Establish defrost repeatability & worst-case variance:** Confirm how consistently defrost cycles occur (timing, duration, and peak air temperature) across normal weekday clinical use when doors are opened during the day.
2. **Verify probe buffering & placement:** Confirm whether the freezer probe is sitting in bare air (or near the evaporator/defrost airflow) vs. inside a physical thermal buffer bottle/block next to stored items, and verify whether actual buffered container temperatures stay safely frozen during defrost.
3. **Verify contents & alarm threshold alignment:**

    - Because normal compressor off-cycles already reach **`-4.2°C to -4.6°C`** every ~2 hours and defrost air reaches **`+7°C to +8°C+`**, verify that nothing sensitive to brief warming above `-10°C` or `0°C` is stored in this auto-defrost compartment.
    - *(Secondary observation for review: on Nov 14, failed calibration log checks on the Medical Fridge recorded `4.6°C` NIST reference vs. `6.29–6.40°C` SCADA reading, and live OPC UA shows `rCalOffset = 0.0°C` on both Fridge and Freezer.)*

### Suggested Action After 3–5 Days of Data
Once we have 5–7 days of continuous logs, we can review the multi-day defrost curves together and decide cleanly between:

- Adding a **physical thermal buffer bottle/block** for the freezer probe (and keeping a modest $\tau$ matching real vial mass),
- Increasing **`tThermalTau`** (e.g., to `30–45 min`) if a `0.0°C` threshold is strictly intended to detect sustained refrigeration failure rather than brief auto-defrost air warmth, or
- Keeping strict sub-zero reagents/specimens in a **manual-defrost freezer** rather than an auto-defrost unit.

# UPS Discharge Test Summary — 2026-11-14

- **Unit Under Test:** Incubator Cabinet UPS (`ups_inc_cab` / `fbUPS02`, APC Smart-UPS 1500 + AP9640 NMC3, `192.168.88.250`)
- **Reference Unit (Remained Online):** Facility Primary UPS (`ups1` / `fbUPS01`, APC Back-UPS ES 600G, `122.0 VAC` input, `13.7 VDC` battery)
- **Raw Data CSV:** [ups_test_20261114_142250.csv](file:///c:/Projects/labSCADA/notes/ups_tests/ups_test_20261114_142250.csv) (`3,170` 1-second data rows; `3,477.63 s` total capture from `14:22:50.432` to `15:20:48.056`)

## Key Events & Observed Ranges

| Metric / Event | Value |
| :--- | :--- |
| Pre-test baseline (`14:22:51`) | `On Line`, Input `123.8 VAC`, Output `123.8 VAC`, Battery `27.6 VDC` (`100.0%`), `79 min` est. |
| Unplug detected (`fbUPS02`) | `14:23:19.374` (`elapsed 28.95 s`, Modbus status `0x0008` → `0x0010`) |
| `Utility Power Lost` alarm (`Cnl 186`) | `14:23:32.290` (`~13 s` after unplug, matching `T#10S` debounce + poll cycle) |
| Test duration on battery captured | `57m 29s` (`14:23:19.374` → `15:20:48.056`) |
| **Inverter Output AC** (on battery) | **`119.4 – 121.4 VAC`** |
| **Input Line AC** (on battery) | **`0.0 VAC`** (`HR[17]` = `0`) |
| **Battery DC Voltage** (on battery, `0.1 V` CLI) | **`27.6 VDC`** (float) → **`26.7 VDC`** (step) → **`24.0 VDC` min** (`24.5 VDC` at stop) |
| **Battery SoC** (on battery) | `100.0%` → **`36.0%` min** (`38.0%` at stop, `24–29 min` est. runtime) |
| **Inverter Load** (on battery) | `5.2% – 20.8%` W (`0.44 – 1.94 A`, incubator heaters cycling) |

## Milestones (5-Minute Intervals)

| Local Time | Elapsed | Input AC | Output AC | Battery DC | SoC | Est. Runtime | Load (W / A) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `14:22:51` | `1.04 s` | `123.8 V` | `123.8 V` | `27.6 V` | `100.0%` | `79 m` | `6.5%` / `1.05 A` |
| `14:27:50` | `300.02 s` | `0.0 V` | `120.1 V` | `24.7 V` | `83.0%` | `65 m` | `11.0%` / `1.33 A` |
| `14:32:50` | `600.06 s` | `0.0 V` | `120.1 V` | `25.3 V` | `82.0%` | `82 m` | `13.0%` / `0.44 A` |
| `14:37:50` | `900.09 s` | `0.0 V` | `120.7 V` | `25.1 V` | `76.0%` | `61 m` | `9.1%` / `1.16 A` |
| `14:42:50` | `1199.74 s` | `0.0 V` | `120.7 V` | `25.1 V` | `74.0%` | `54 m` | `16.2%` / `1.05 A` |
| `14:47:50` | `1499.58 s` | `0.0 V` | `120.1 V` | `25.1 V` | `71.0%` | `69 m` | `13.0%` / `0.50 A` |
| `14:52:50` | `1800.45 s` | `0.0 V` | `120.1 V` | `24.8 V` | `65.0%` | `59 m` | `11.0%` / `0.77 A` |
| `14:57:50` | `2100.26 s` | `0.0 V` | `120.1 V` | `24.7 V` | `59.0%` | `38 m` | `9.7%` / `1.50 A` |
| `15:02:50` | `2399.95 s` | `0.0 V` | `120.7 V` | `24.8 V` | `55.0%` | `39 m` | `14.9%` / `0.94 A` |
| `15:07:50` | `2699.75 s` | `0.0 V` | `120.1 V` | `24.7 V` | `50.0%` | `28 m` | `13.0%` / `1.27 A` |
| `15:12:50` | `3000.05 s` | `0.0 V` | `120.1 V` | `24.5 V` | `45.0%` | `29 m` | `17.5%` / `1.72 A` |
| `15:17:50` | `3300.17 s` | `0.0 V` | `120.1 V` | `24.5 V` | `41.0%` | `33 m` | `11.7%` / `1.00 A` |
| `15:20:48` | `3477.63 s` | `0.0 V` | `120.1 V` | `24.5 V` | `38.0%` | `29 m` | `14.3%` / `1.27 A` |

## Register Mapping Finding (`afoa-incu-ups` Modbus)

- **`HR[14]` (`awIncuUpsRegs[14]`):** Tracks inverter **Output Voltage** (`119–120 VAC` during discharge). [PLC_PRG.st](file:///c:/Projects/labSCADA/codesys/src/PLC_PRG.st#L129) currently assigns `awIncuUpsRegs[14] * 10` to `fbUPS02.wLineVoltageX10` (`Cnl 184`).
- **`HR[17]` (`awIncuUpsRegs[17]`):** Tracks utility **Input Line Voltage** (`123 VAC` on line → `0 VAC` while unplugged).


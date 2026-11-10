# LabSCADA Cryo Dewar Touchscreen Node (2.8" ESP32-S3)

Dedicated firmware for the **Hosyond / Guition 2.8" Capacitive Touch Display Module** (ESP32-S3) with **MAX31865 RTD (PT100/PT1000)** cryogenic monitoring and ESP-NOW wireless telemetry to Rapid SCADA.

This crate is completely isolated from the standard Seeed Studio XIAO sensor nodes in `crates/node`.

---

## 1. Hardware Pinout & Wiring

### A. 4-Wire SPI to MAX31865 (Back 4-Pin Header)
All 4 SPI signals plug directly into the 4-pin expansion header on the back:

| Board Pin | SPI Signal | MAX31865 Pin | Function |
| :--- | :--- | :--- | :--- |
| **`IO2`** | `SCK` | `SCK` / `CLK` | SPI Clock |
| **`IO3`** | `MOSI` | `SDI` / `MOSI` | Configuration register writes |
| **`IO14`** | `MISO` | `SDO` / `MISO` | 15-bit RTD resistance data read |
| **`IO21`** | `CS` | `CS` | Chip Select |
| *I2C header* | `3.3V` | `VIN` / `3V3` | 3.3V power |
| *I2C header* | `GND` | `GND` | Ground reference |

*(Note: If testing temporarily with a 3-wire MAX31855 thermocouple before your MAX31865 arrives, wire `SCK` to `IO2`, `MISO` to `IO14`, `CS` to `IO21`, and leave `IO3` disconnected).*

### B. Display, Touch & Battery (Internal Onboard Connections)
* **Backlight:** `GPIO 45` (driven LOW for 0 mA black screen, HIGH when touched or during alarm)
* **Touch Interrupt:** `GPIO 17` (`TP_INT`, active-low interrupt from FT6336G capacitive glass)
* **Touch I2C:** `GPIO 15` (`SCL`), `GPIO 16` (`SDA`)
* **Display SPI:** `GPIO 10` (`CS`), `GPIO 11` (`MOSI`), `GPIO 12` (`SCK`), `GPIO 46` (`DC`)
* **Battery ADC:** `GPIO 9` (`BAT_ADC`, pre-wired onboard 2:1 resistor divider to LiPo connector)

---

## 2. Operating Modes & Features

1. **Touch to Wake:**
   - Display backlight (`GPIO 45`) is completely dark to preserve battery.
   - The moment an embryologist touches the glass, `GPIO 17` triggers an interrupt and turns on the backlight.
   - Screen stays awake for **15 seconds** after the last touch, then turns off automatically.
2. **Clinical Excursion Override:**
   - If cryogenic temperature rises above **$-135.0^\circ\text{C}$** (USP $\langle 1079 \rangle$), the screen overrides sleep, turns the backlight ON, flashes a bold red alarm, and transmits high-priority telemetry immediately.
3. **On-Screen Tank Fill Hold:**
   - Tapping the on-screen **"FILL HOLD"** button activates a 30-minute maintenance hold to prevent nuisance alarms during liquid nitrogen replenishment.
4. **Seamless SCADA Telemetry:**
   - Transmits `DeviceTelemetry::Dewar` over ESP-NOW every 20 seconds, perfectly matching the LabSCADA bridge and Rapid SCADA Modbus mapping.

---

## 3. How to Build & Flash

Open PowerShell in the `wireless` folder:

```powershell
# 1. Source the Espressif toolchain environment
. 'C:\Users\bobos\export-esp.ps1'

# 2. Build the release binary
cargo +esp build --release -p dewar-display

# 3. Flash to board over USB Type-C and monitor serial output
espflash flash target/xtensa-esp32s3-none-elf/release/dewar-display --monitor
```


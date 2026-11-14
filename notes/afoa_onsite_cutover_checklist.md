# AFOA Onsite Cutover & Commissioning Checklist

Living checklist of every configuration change, IP update, and hardware verification needed when moving the **WAGO 752-9401 (`afoa-scada`)** and **APC Back-UPS ES 600G** from the home bench (`192.168.10.0/24`) to the AFOA clinic (`192.168.88.0/24`), and commissioning physical clinic I/O.

---

## 1. Network & Hardware Cutover (`afoa-scada` WAGO 752-9401)

* **Ethernet Port (`X1` vs `X2`):**
  * **Clinic LAN port:** Plug the clinic switch drop into **`X1`** (MAC `00:30:de:46:fd:04`). NetworkManager profile `X1` is already preconfigured:
    * Method: `manual` (`autoconnect=yes`)
    * Address: `192.168.88.252/24`
    * Gateway / DNS: `192.168.88.1`
  * **Home bench port:** Leave **`X2`** (MAC `00:30:de:46:fd:05`, DHCP `192.168.10.34`) unplugged onsite to avoid dual default routes.
* **DNS & DHCP Hygiene (MikroTik RB5009 — `192.168.88.1`):**
  * `afoa-scada.labmon` resolves to `192.168.88.252`.
  * `afoa-plc.labmon` resolves to `192.168.88.253`.
  * `afoa-node00.labmon` resolves to `192.168.88.251`.
  * Clinic DHCP pool is narrowed to `192.168.88.10–200` so `.251–.253` static nodes cannot collide.
  * Retired Pi (`afoa-scada-og`, MAC `2c:cf:67:ed:38:cf`) has `eth0` set to DHCP and SCADA services disabled; confirm no stale RB5009 static lease still pins `.252` to the Pi's MAC.
* **USB UPS Connection:**
  * Reconnect the **APC Back-UPS ES 600G** USB cable directly to the `752-9401` onsite.
  * Verify NUT and the Modbus TCP server bridge come back cleanly:
    ```bash
    upsc apc@localhost
    systemctl is-active nut-driver@apc nut-server nut-monitor ups-modbus-bridge
    ```

---

## 2. CODESYS (`AFOA.project`) — Onsite Changes Before Go-Live

> **Terminology:** In this system, the PLC (`afoa-plc.labmon`, WAGO 750-8212) acts as the **Modbus TCP Client** polling external **Modbus TCP Servers** (`afoa-scada` UPS bridge and `afoa-node00`). *(Note: CODESYS's legacy device tree icons label these Client/Server roles.)*

### A. `UPS_SCADA` — Switch SCADA UPS Modbus TCP Server IP (Home Bench → Clinic)

* **CODESYS Device Tree Name:** `UPS_SCADA` (maps to `fbUPS01 : FB_APC_SmartUPS`)
* **Home bench testing IP:** `192.168.10.34` (Port `502`)
* **Onsite change required:** Change **`UPS_SCADA`**'s target IP in `AFOA.project` to **`192.168.88.252`** (Port `502`), rebuild, and download to `afoa-plc.labmon`.

**Reference — `UPS_SCADA` Channel & I/O Mapping (`fbUPS01 : FB_APC_SmartUPS`):**
*(Bridge source: `scripts/ups_modbus_server.py` running via `ups-modbus-bridge.service` on `0.0.0.0:502`)*

* **Read Channel:** `FC 03` Read Holding Registers, Offset `16#0000` (`0`), Length **`8`** words (`40001–40008`), Cyclic (`1000 ms`)
* **Write Channel:** `FC 06` Write Single Register (or `FC 16`), Offset `16#0009` (`9` / `40010`), Length **`1`** word
* **Always update variables:** `Enabled 2 (always in bus cycle task)`

| Channel / Word | Register | `PLC_PRG` Variable |
| :--- | :---: | :--- |
| Read — Word 0 | `40001` | `Application.PLC_PRG.fbUPS01.wStatusWord` |
| Read — Word 1 | `40002` | `Application.PLC_PRG.fbUPS01.wBatteryPct` |
| Read — Word 2 | `40003` | `Application.PLC_PRG.fbUPS01.wRuntimeSec` |
| Read — Word 3 | `40004` | `Application.PLC_PRG.fbUPS01.wLineVoltageX10` |
| Read — Word 4 | `40005` | `Application.PLC_PRG.fbUPS01.wLoadPct` |
| Read — Word 5 | `40006` | *(Leave unmapped — Battery V ×10)* |
| Read — Word 6 | `40007` | `Application.PLC_PRG.fbUPS01.wRuntimeMin` |
| Read — Word 7 | `40008` | `Application.PLC_PRG.fbUPS01.wBeeperStatus` |
| Write — Word 0 | `40010` | `Application.PLC_PRG.fbUPS01.wCommandOut` |

---

### B. `INC_CAB` — Incubator Cabinet (`afoa-node00.labmon` — `192.168.88.251:502`)

* **CODESYS Device Tree Name:** `INC_CAB`

Verified live K-Bus modules on `afoa-node00`:
* `750-352` 2-Port Switched Coupler (`0x0160`, MAC `00:30:DE:07:30:6B`, FW `01.03.09 (04)`) *(replaced `750-341` `0x0155`)*
* 8-ch Digital Input module (`0x8801` → `8` DI bits; `DI 8` = Cabinet 01 Door Switch)
* 8-ch Digital Output module (`0x8802` → `8` DO bits)
* `750-461` 2-ch Pt100 RTD Input module (`0x01CD` → `32` AI bits / `2` words; Ch 1 = Cabinet 01 Temp `Cnl 110`)
* `0` Analog Outputs

**Modbus TCP Server Configuration in `AFOA.project` (`192.168.88.251`, Port `502`):**
* **Read Channel:** `FC 02` Read Discrete Inputs, Offset `16#0000` (`0`), Length **`8`** bits (`Bit 0–7` = physical `DI 1–8`)
* **Write Channel (optional until fan/strobe wired):** `FC 15` Write Multiple Coils, Offset `16#0000` (`0`), Length **`8`** bits (`Bit 0–7` = physical `DO 1–8`)
* **Always update variables:** `Enabled 2 (always in bus cycle task)`

**Onsite Physical I/O & Standardized Fail-Safe Door Wiring:**
> **Standard:** All door inputs standardize on fail-safe NC 24V loops mapped **directly** to `.bDoorClosed` (zero shadow variables or software inversion):
> **`bDoorClosed = TRUE` (24V loop closed) when Door is CLOSED** · **`bDoorClosed = FALSE` (0V / open loop) when Door is OPEN or disconnected**.

1. **Cabinet Door Switch (`fbCabinet01 : FB_IncubatorCabinet`):**
   * `INC_CAB` DI bit is mapped directly to `Application.PLC_PRG.fbCabinet01.bDoorClosed`.
   * **Current temporary override in `PLC_PRG`:** `bDoorClosed := TRUE` (`//TODO: switch wiring on door`) because the switch currently reads `FALSE` when closed.
   * **Onsite rewiring:** Rewire the cabinet door switch to **NC** (`TRUE` when closed, `FALSE` when open), then **remove `bDoorClosed := TRUE`** from `fbCabinet01(...)` in `PLC_PRG` so the physical `INC_CAB` DI isn't overwritten.
2. **Cleanroom Doors (`fbDoor01`, `fbDoor02 : FB_FacilityDoor` — CODESYS `DOOR_DI`):**
   * `DOOR_DI` K-Bus DI channels map directly to `Application.PLC_PRG.fbDoor01.bDoorClosed` and `Application.PLC_PRG.fbDoor02.bDoorClosed` (no intermediate `bDoor01`/`bDoor02` booleans).
   * **Door 02 (`fbDoor02`):** Already reading `TRUE` (`1.000`) from hardware when closed — no rewiring needed (still verify open/close test onsite).
   * **Door 01 (`fbDoor01`) — current temporary override in `PLC_PRG`:** `bDoorClosed := TRUE` (`//TODO: switch wiring on door`) because Door 01 currently reads `FALSE` when closed.
   * **Onsite rewiring:** Rewire Door 01 contact to **NC** (`TRUE` when closed, `FALSE` when open), then **remove `bDoorClosed := TRUE`** from `fbDoor01(...)` in `PLC_PRG`.
3. **G210 Incubator Alarm Contacts (`fbIncubator1`, `fbIncubator2 : FB_G210_Incubator`):**
   * `bAlarmContact` expects **`FALSE` = Normal, `TRUE` = Alarm**.
   * Verify physical terminal assignments (whether on `INC_CAB` DI or local `DOOR_DI` K-Bus) and test an alarm contact + verify `fbCabinet01.bIncubatorMute` suppresses it when the cabinet door opens.

---

## 3. Temporary Placeholders & Future Hardware Upgrades

Currently configured as non-wireless placeholders until clinic sensors/nodes are installed:

* **Cold Storage & Dewars 2–5 (`PLC_PRG` + `sites/afoa/equipment.json`):**
  * `fbColdStorage` and `fbDewar2`..`fbDewar5` currently run with `bIsWireless := FALSE` / `"is_wireless": false` and standby nominal temperatures (`3.5°C`, `-20.0°C`, `25.0°C`, `-150.0°C`). *(Dewar 1 is discontinued and removed.)*
  * **When wireless nodes are installed onsite:** Update Modbus/register mappings, set `bIsWireless := TRUE` in `PLC_PRG` and `"is_wireless": true` in `sites/afoa/equipment.json`, then run `./deploy_site.sh afoa`.
* **Incubator Cabinet Exhaust Fan (`INC_CAB` / `afoa-node00`):**
  * Cabinet RTD temperature (`750-461` Ch 1 → `fbCabinet01.rProcessTemp` / `Cnl 110`) and door contact (`DI 8` → `Cnl 132`) are live; the exhaust fan relay output remains deferred (`fan_command_cnl: null` in `sites/afoa/equipment.json` keeps it hidden in the Kiosk UI while PLC/backend logic stays intact).
  * **When fan relay is added:** Wire to `750-530` DO 1 (`fbCabinet01.bFanCommand`), add the OPC UA tag to `DrvOpcUa_001.xml`, and populate `fan_command_cnl` in `sites/afoa/equipment.json`.
* **Incubator Cabinet Ethernet UPS (Future):**
  * Add a second `FB_APC_SmartUPS` (or SNMP/Modbus TCP UPS) instance and Modbus TCP server entry alongside `UPS_SCADA` when ready to monitor the cabinet UPS.

---

## 4. Final Onsite Verification Checklist

- [ ] `afoa-scada` plugged into `X1` at `192.168.88.252`, `X2` unplugged, internet & DNS working
- [ ] All systemd units `active` on `afoa-scada`:
  `postgresql`, `scadaserver6`, `scadacomm6`, `scadaweb6`, `scadaagent6`, `ivf-alert-engine`, `cloudflared`, `nut-server`, `ups-modbus-bridge`
- [x] `afoa-plc` (`192.168.88.253`) Modbus TCP Client polling **`INC_CAB`** (`afoa-node00` `750-352`, `192.168.88.251`) verified live (`Cnl 110` temp & `Cnl 132` door); verify **`UPS_SCADA`** (`192.168.88.252`) onsite
- [ ] Rewire `fbCabinet01` (`INC_CAB`) and `fbDoor01` (`DOOR_DI`) switches to **NC** (`bDoorClosed = TRUE` when closed, `FALSE` when open) and **remove the temporary `bDoorClosed := TRUE` overrides** from `PLC_PRG` (`fbDoor02` already reads `TRUE` when closed)
- [ ] Kiosk UI loads locally (`http://192.168.88.252:8080` / kiosk browser) and externally (`https://komdivflab.larestelemetry.com/`)
- [ ] Physical door open/close tests verified on Cleanroom Doors 01/02 and Cabinet 01 + UPS unplug test confirms `On Battery` telemetry and Pushover notification


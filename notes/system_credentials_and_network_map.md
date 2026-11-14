# IVF Lab SCADA: System Credentials & Network Device Map

> [!CAUTION]
> **CONFIDENTIAL LAB INFRASTRUCTURE DOCUMENTATION**
> This document records device addresses, operational credentials, service accounts, and network mappings for the IVF Lab SCADA Telemetry and Control system. Keep this repository secure.

---

## 1. Hardware & Network Inventory

| Device Name | Device Model | MAC Address | Bench IP (`.lan`) | Lab Domain (`.labmon`) | Primary Roles / Services |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`afoa-plc`** (`plc0000`) | **WAGO PFC200 (750-8212)** | `00:30:DE:7C:EF:9A` | `192.168.10.139` | `afoa-plc.labmon` (`192.168.88.253`) | Primary PLC, K-Bus I/O, CODESYS V3.5, OPC UA Server (:4840), WBM (:443) |
| **`afoa-scada`** (`scadapi02`)| **Raspberry Pi 4 (8GB)** | `88:A2:9E:12:0E:1D` (Wi-Fi)<br>`88:A2:9E:12:0E:1C` (Eth)<br>`2C:CF:67:ED:38:CF` (AFOA) | `192.168.10.133` | `afoa-scada.labmon` (`192.168.88.252`) | Rapid SCADA 6.x, PostgreSQL 17, Grafana, IVF Alert Engine (:8080), LN2 Kiosk |
| **`afoa-node00`** (`INC_CAB`) | **WAGO Coupler (750-352)** | `00:30:DE:07:30:6B` | — | `afoa-node00.labmon` (`192.168.88.251`) | 2-Port Switched Modbus TCP Coupler for Incubator Cabinet (`750-431` DI, `750-530` DO, `750-461` RTD) (:502, :80) |
| **`afoa-incu-ups`** (`UPS_INC_CAB`) | **APC Smart-UPS 1500 + AP9640 NMC3** | `28:29:86:64:07:FE` | — | `afoa-incu-ups.labmon` (`192.168.88.250`) | Incubator Cabinet Backup UPS; native Modbus TCP (`502/TCP`), SSH (:22), HTTPS (:443) |
| **`bobslaptop`** | **Technician Laptop** | *Per Adapter* | `192.168.10.x` | `bobslaptop.labmon` (`192.168.88.254`) | Engineering Workstation, CODESYS V3.5 IDE, WAGO Ethernet Settings |
| **`codesyspi02`** | **Raspberry Pi 4 (4GB)** | `DC:A6:32:6F:3F:B4` (Wi-Fi)<br>`DC:A6:32:6F:3F:B3` (Eth) | `192.168.10.135` | `codesyspi02.labmon` | Secondary / Development CODESYS SoftPLC, OPC UA Server (:4840) |
| **`router`** | **MikroTik RouterOS** | *Per WAN/LAN* | `192.168.10.1` | Gateway Router (`192.168.88.1`) | Static DNS Server (`.labmon`), DHCP Server (`bootp-support=static`), Firewall |

---

## 2. Credentials & Service Accounts

### A. WAGO PFC200 Controller (`afoa-plc` / `plc0000`)
* **Host / Device:** `afoa-plc.labmon` (IP: `192.168.88.253`)
* **Operating System:** WAGO Embedded Real-Time Linux (Firmware 24+)
* **User Accounts:**
  * **`root`** (Linux Superuser / Console / SSH):
    - **Password:** `labMon@2026`
    - **Access:** Direct shell, system daemon control, package updates
  * **`scada`** (Service Account for Rapid SCADA / OPC UA):
    - **Password:** `labMon@2026`
    - **Groups:** `admin`
    - **Purpose:** Secure automated OPC UA client sessions (`SignAndEncrypt` / `Basic256Sha256`)
  * **`admin`** (Web-Based Management WBM / Factory Admin / OPC UA):
    - **Password:** `labMon@2026`
    - **Access:** WBM Web GUI (`https://afoa-plc.labmon/` or `https://192.168.88.253/`), SSH, and OPC UA client authentication
* **Active Network Ports:**
  * `443/TCP`: WAGO Web-Based Management (HTTPS WBM)
  * `22/TCP`: Secure Shell (SSH)
  * `4840/TCP`: CODESYS Embedded OPC UA Server
  * `11740/TCP`: CODESYS V3.5 Programming & Runtime Gateway

---

### B. WAGO 750-352 Ethernet Fieldbus Coupler (`afoa-node00` / `INC_CAB`)
* **Host / Device:** `afoa-node00.labmon` (IP: `192.168.88.251`)
* **Device Role:** 2-Port Switched Modbus TCP Fieldbus Coupler for Incubator Cabinet `INC_CAB` (`750-431` 8-ch DI, `750-530` 8-ch DO, `750-461` 2-ch Pt100 RTD)
* **MAC Address:** `00:30:DE:07:30:6B` *(replaced retired `750-341` MAC `00:30:DE:02:7B:71`)*
* **Firmware Revision:** `01.03.09 (04)`
* **Network Assignment:** Static IP assigned in EEPROM (`192.168.88.251`, Mask `255.255.255.0`, Gateway `192.168.88.1`, `PCFGIP=EEPROMIP`), **all 8 DIP switches `OFF` (`0`)**
* **Protocol Settings (`Port.ssi`):** `Modbus TCP (502)`, `Modbus UDP (502)`, `HTTP (80)`, `FTP (21)`, and `WAGO Services (6626)` enabled; `Ethernet IP` (`44818/2222`), `SNMP`, `BootP`, and `DHCP` disabled
* **User Accounts:**
  * **`admin`**: Factory default `wago` (kept as default)
  * **`user`**: Factory default `user`
* **Active Network Ports:**
  * `80/TCP`: WAGO Web-Based Management (`http://192.168.88.251/`)
  * `502/TCP` & `502/UDP`: Modbus Server (K-Bus register access)
  * `6626/TCP`: WAGO Services (`WAGO Ethernet Settings`)
* **Config Backup:** [sites/afoa/nodes/afoa-node00_0030DE07306B.md](file:///c:/Projects/labSCADA/sites/afoa/nodes/afoa-node00_0030DE07306B.md) (legacy `750-341` `.wes` archived in [legacy/](file:///c:/Projects/labSCADA/sites/afoa/nodes/legacy/afoa-node00_0030DE027B71.wes))

---

### B2. Incubator Cabinet Backup UPS (`afoa-incu-ups` / APC Smart-UPS 1500)
* **Host / Device:** `afoa-incu-ups.labmon` (IP: `192.168.88.250`)
* **UPS Hardware:** APC Smart-UPS 1500 (`AS1030142941`, Firmware `653.18.D`, Manufacture `07/22/10`)
* **Network Management Card:** APC AP9640 NMC3 (`ZA2211002838`, HW Rev `5`, AOS/APP `v1.5.1.1`, MAC `28:29:86:64:07:FE`)
* **Network Assignment:** Static IPv4 (`192.168.88.250`, Mask `255.255.255.0`, Gateway `192.168.88.1`, Boot Mode `Manual`)
* **User Account:** `apc` / `LABMON`
* **Active Network Ports:**
  * `502/TCP`: Native Modbus TCP Slave (`Unit ID 1`, polled read-only by `afoa-plc` `fbUPS02`, `FC 03 offset 0 len 20`)
  * `22/TCP`: SSH CLI
  * `443/TCP`: HTTPS NMC Web UI (`https://192.168.88.250/`)
* **Dashboard & Control Notes:** Read-only telemetry (`Cnl 181–187`) nested inside `Incubator Cabinet 01`; remote beeper mute disabled.

---

### C. SCADA Server & Database (`afoa-scada` / `scadapi02`)
* **Host:** `afoa-scada.labmon` (IP: `192.168.88.252`)
* **Operating System:** Debian Linux (arm64)
* **Linux Host User:**
  * **Username:** `bobostrom`
  * **Password:** `cycleB0b` (sudo enabled)
* **PostgreSQL Database (`rapid_scada` on Port 5432):**
  * **Database Name:** `rapid_scada`
  * **Administrator User:** `postgres` / `postgres`
  * **Grafana Reader User:** `grafana_reader` / `scada` (Read-only on `mod_arc_postgre_sql.*` and `public.ln2_tank_logs`)
* **Rapid SCADA 6.x Webstation & Server:**
  * **Admin Webstation User:** `admin` / `scada` (Port 10000 / 10008)
  * **Admin Service User:** `ScadaAdmin`
* **IVF Clinical Alert Engine & LN2 Kiosk:**
  * **URL:** `http://afoa-scada.labmon:8080/`
  * **Daemon Service:** `ivf-alert-engine.service`
  * **Pushover Emergency Sirens:** Priority 2 (Clinical Excursions), Priority 0 (Daily QA Test)

---

### D. Raspberry Pi CODESYS Development PLC (`codesyspi02`)
* **Host:** `codesyspi02` (IP: `192.168.10.135`)
* **Operating System:** Raspberry Pi OS Linux (arm64)
* **Linux Host User:**
  * **Username:** `bobostrom`
* **CODESYS Device User Management:**
  * **Username:** `scada`
  * **Password:** `labMon@2026`
* **Active Network Ports:**
  * `22/TCP`: SSH
  * `4840/TCP`: CODESYS OPC UA Server
  * `11740/TCP`, `1217/TCP`: CODESYS Runtime communication

---

## 3. Rapid SCADA OPC UA Driver Configuration Reference

Inside [sites/afoa/scada_config/DrvOpcUa_line001.xml](file:///c:/Projects/labSCADA/sites/afoa/scada_config/DrvOpcUa_line001.xml) and `/opt/scada/ScadaComm/Config/DrvOpcUa_line001.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<OpcLineConfig>
  <ConnectionOptions>
    <ServerUrl>opc.tcp://afoa-plc.labmon:4840</ServerUrl>
    <SecurityMode>None</SecurityMode>
    <SecurityPolicy>None</SecurityPolicy>
    <AuthenticationMode>Username</AuthenticationMode>
    <Username>admin</Username>
    <Password>B36BADF251C4B59A5E5A72B9E1574492</Password> <!-- Encrypted labMon@2026 -->
  </ConnectionOptions>
</OpcLineConfig>
```

> **Note on Password Encryption:** In Rapid SCADA XML configurations, the plaintext password `labMon@2026` is stored using Rapid SCADA's standard reversible encryption format as hex string: `B36BADF251C4B59A5E5A72B9E1574492`.

### WAGO 750-8212 OPC UA NodeID Naming Convention
Unlike generic soft-PLCs, the embedded CODESYS runtime on the WAGO 750-8212 publishes symbols under the device description string:
* **Prefix:** `ns=4;s=|var|WAGO 750-8212 PFC200 G2 2ETH RS.Application.PLC_PRG.`
* **Example:** `ns=4;s=|var|WAGO 750-8212 PFC200 G2 2ETH RS.Application.PLC_PRG.rLabAmbientTemp`

Configured in [sites/afoa/scada_config/DrvOpcUa_001.xml](file:///c:/Projects/labSCADA/sites/afoa/scada_config/DrvOpcUa_001.xml) and `/opt/scada/ScadaComm/Config/DrvOpcUa_001.xml`.

> **Core Architectural Rule (Single Source of Truth):**
> All fieldbus polling, timers, and alarm gating **MUST** go strictly through the **WAGO PFC200 (750-8212)** controller (`afoa-plc.labmon`). Remote fieldbus couplers (such as `afoa-node00.labmon` 750-352) are polled exclusively by the `-8212` PLC over Modbus TCP. Neither Rapid SCADA nor `ivf_alert_engine.py` should ever bypass the `-8212` to poll remote couplers directly. All telemetry flows:
> `Remote Coupler` $\rightarrow$ `750-8212 PLC (CODESYS)` $\rightarrow$ `OPC UA (:4840)` $\rightarrow$ `ScadaComm` $\rightarrow$ `PostgreSQL (curcopy_current)` $\rightarrow$ `Alert Engine & Kiosk`.

---

## 4. Operational Maintenance & Transition Commands

### Check Live Communication Line Status:
```bash
tail -f /var/log/scada/ScadaComm/Log/line001.log
```

### Restart Rapid SCADA Communicator:
```bash
echo cycleB0b | sudo -S systemctl restart scadacomm6
```

### Query Live Telemetry Values from PostgreSQL:
```bash
PGPASSWORD=postgres psql -h localhost -U postgres -d rapid_scada -c \
  "SELECT cnl_num, time_stamp, val, stat FROM mod_arc_postgre_sql.curcopy_current WHERE cnl_num IN (101, 102, 103, 104, 125);"
```

### Test Clinical Alert Engine Status:
```bash
curl -s http://afoa-scada.labmon:8080/api/status | jq .
```

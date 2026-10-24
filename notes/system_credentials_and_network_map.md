# IVF Lab SCADA: System Credentials & Network Device Map

> [!CAUTION]
> **CONFIDENTIAL LAB INFRASTRUCTURE DOCUMENTATION**
> This document records device addresses, operational credentials, service accounts, and network mappings for the IVF Lab SCADA Telemetry and Control system. Keep this repository secure.

---

## 1. Hardware & Network Inventory

| Device Name | Device Model | MAC Address | Bench IP (`.lan`) | Lab Domain (`.labmon`) | Primary Roles / Services |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`plc0000`** | **WAGO PFC200 (750-8212)** | `00:30:DE:7C:EF:9A` | `192.168.10.139` | `plc0000.labmon` | Primary PLC, K-Bus I/O, CODESYS V3.5, OPC UA Server (:4840), WBM (:443) |
| **`scadapi02`** | **Raspberry Pi 4 (8GB)** | `88:A2:9E:12:0E:1D` (Wi-Fi)<br>`88:A2:9E:12:0E:1C` (Eth) | `192.168.10.133` | `scadapi02.labmon` | Rapid SCADA 6.x, PostgreSQL 17, Grafana, IVF Alert Engine (:8080), LN2 Kiosk |
| **`codesyspi02`** | **Raspberry Pi 4 (4GB)** | `DC:A6:32:6F:3F:B4` (Wi-Fi)<br>`DC:A6:32:6F:3F:B3` (Eth) | `192.168.10.135` | `codesyspi02.labmon` | Secondary / Development CODESYS SoftPLC, OPC UA Server (:4840) |
| **`router`** | **MikroTik RouterOS** | *Per WAN/LAN* | `192.168.10.1` | Gateway Router | DHCP Server, DNS Server (`IP -> DNS -> Static`), Firewall |

---

## 2. Credentials & Service Accounts

### A. WAGO PFC200 Controller (`plc0000`)
* **Host / Device:** `plc0000` (IP: `192.168.10.139`)
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
    - **Access:** WBM Web GUI (`https://plc0000/` or `https://192.168.10.139/`), SSH, and OPC UA client authentication
* **Active Network Ports:**
  * `443/TCP`: WAGO Web-Based Management (HTTPS WBM)
  * `22/TCP`: Secure Shell (SSH)
  * `4840/TCP`: CODESYS Embedded OPC UA Server
  * `11740/TCP`: CODESYS V3.5 Programming & Runtime Gateway

---

### B. SCADA Server & Database (`scadapi02`)
* **Host:** `scadapi02` (IP: `192.168.10.133`)
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
  * **URL:** `http://scadapi02:8080/`
  * **Daemon Service:** `ivf-alert-engine.service`
  * **Pushover Emergency Sirens:** Priority 2 (Clinical Excursions), Priority 0 (Daily QA Test)

---

### C. Raspberry Pi CODESYS Development PLC (`codesyspi02`)
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

Inside [scada_config/ScadaComm/DrvOpcUa_line001.xml](file:///home/bobostrom/Projects/labSCADA/scada_config/ScadaComm/DrvOpcUa_line001.xml) and `/opt/scada/ScadaComm/Config/DrvOpcUa_line001.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<OpcLineConfig>
  <ConnectionOptions>
    <ServerUrl>opc.tcp://plc0000:4840</ServerUrl>
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

Configured in [scada_config/ScadaComm/DrvOpcUa_001.xml](file:///home/bobostrom/Projects/labSCADA/scada_config/ScadaComm/DrvOpcUa_001.xml) and `/opt/scada/ScadaComm/Config/DrvOpcUa_001.xml`.

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
  "SELECT cnl_num, time_stamp, val, stat FROM mod_arc_postgre_sql.curcopy_current WHERE cnl_num IN (101, 102, 103, 125);"
```

### Test Clinical Alert Engine Status:
```bash
curl -s http://127.0.0.1:8080/api/status | jq .
```

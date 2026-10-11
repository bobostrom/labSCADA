# Network Lab Configuration Notes: MikroTik RouterOS v7

## 1. Environment & Topology Overview
*   **Router Model:** MikroTik RB5009UPR+S+IN
*   **Private Lab Subnet:** `192.168.88.0/24` (All internal ports assigned to master `bridge`)
*   **Local DNS Suffix:** `.labmon`
*   **Core Lab Devices:** 
    *   `labSCADA` (SCADA Host PC / Raspberry Pi running in Antigravity IDE)
    *   `labRTAC` (SEL Real-Time Automation Controller - Dynamic DHCP client)
*   **WAN Interfaces (Failover Topology):**
    *   **Primary WAN (`ether1`):** Corporate Network drop (Distance `1` - Higher Priority)
    *   **Backup WAN (`ether2`):** Cellular Hotspot (Distance `2` - Standby Priority)

---

## 2. Interface List & NAT Setup (Firewall Security)
To ensure firewall rules seamlessly apply to whichever internet path is active, interfaces are grouped into the global `WAN` list.

### Step 1: Secure Port 2
Ensure `ether2` is **removed** from the local bridge ports (`Bridge` > `Ports`) so it acts as a dedicated, routed internet port and does not bridge your private lab data back out to the hotspot network.

### Step 2: Add Ports to WAN List
Navigate to `Interfaces` > `Interface List` and add both internet-facing ports:
*   List: `WAN` | Interface: `ether1`
*   List: `WAN` | Interface: `ether2`

### Step 3: Outbound Masquerade Rule
Navigate to `IP` > `Firewall` > `NAT` and ensure a single rule handles all outbound traffic:
*   **Chain:** `srcnat`
*   **Out. Interface List:** `WAN`
*   **Action:** `masquerade`

---

## 3. Distance-Based Dual WAN Failover
This architecture automatically routes internet traffic through the cellular hotspot when corporate is missing, but instantly switches to the corporate line the second a cable is connected to port 1.

Navigate to `IP` > `DHCP Client` and configure both links:

1.  **Corporate Primary (`ether1`):** 
    *   Add Default Route: `yes`
    *   Advanced > Default Route Distance: **`1`**
2.  **Cellular Backup (`ether2`):** 
    *   Add Default Route: `yes`
    *   Advanced > Default Route Distance: **`2`**

---

## 4. DHCP-to-DNS Automation Script (.labmon)
Because industrial equipment like the SEL RTAC may have its IP changed by DHCP, a script updates the MikroTik’s Static DNS records automatically every time a lease is claimed or renewed.

### Step 1: Configure Core DNS Server
Navigate to `IP` > `DNS`:
*   Check **Allow Remote Requests**.

### Step 2: Add Automation Script to DHCP Server
1.  Navigate to `IP` > `DHCP Server` > `DHCP` tab.
2.  Double-click your active DHCP server profile (e.g., `dhcp1`).
3.  Click the **Script** tab and paste the following code block:

```routeros
:local zone "labmon"
:local hostname $"lease-hostname"
:if ([:len $hostname] = 0) do={ :set hostname $"host-name" }

:if ([:len $hostname] > 0) do={
    :local dnsName ($hostname . "." . $zone)
    /ip/dns/static/remove [find name=$dnsName]
    
    :if ($leaseBound = 1) do={
        /ip/dns/static/add name=$dnsName address=$leaseActIP ttl=00:05:00 comment="DHCP Dynamic Lease"
    }
}
```

### Step 3: Push Suffix & DNS to Clients
Navigate to `IP` > `DHCP Server` > `Networks` tab, open your subnet profile (`192.168.88.0/24`), and set:
*   **DNS Servers:** `192.168.88.1` (Forces clients to query the MikroTik)
*   **Domain:** `labmon` (Appends the `.labmon` search domain suffix automatically)

---

## 5. Verifying Active Connections & Routing Status

To verify which path your traffic is taking, run a print command in the MikroTik **New Terminal** window:

```text
/ip/route/print
```

### Example Verification Log (Active Corporate Link Live)
Below is the validated route output showcasing the distances in effect. The Corporate connection (`172.16.10.1` on `ether1`) successfully overrides the Cellular line because of its lower distance value (`1` vs `2`), marked by the **`A` (Active)** flag.

```text
[admin@LABMON] > /ip/route/print
Flags: D - DYNAMIC; A - ACTIVE; c - CONNECT, d - DHCP
Columns: DST-ADDRESS, GATEWAY, ROUTING-TABLE, DISTANCE
    DST-ADDRESS      GATEWAY      ROUTING-TABLE  DISTANCE
D d 0.0.0.0/0        192.168.5.1  main                  2
DAd 0.0.0.0/0        172.16.10.1  main                  1
DAc 172.16.10.0/24   ether1       main                  0
DAc 192.168.5.0/24   ether2       main                  0
DAc 192.168.88.0/24  bridge       main                  0
```

### Diagnostic Flags Breakdown:
*   **`DAd 0.0.0.0/0 via 172.16.10.1 (Distance 1)`**: **Active Path.** All internet-bound traffic (such as your outbound SCADA `api.pushover.net` alerts) routes through corporate port `ether1`.
*   **`D d 0.0.0.0/0 via 192.168.5.1 (Distance 2)`**: **Standby Path.** The cellular hotspot remains bound and healthy on `ether2`. It is missing the `A` flag, indicating it is safely sleeping until needed.

---

## 6. Client Station Verification (PowerShell)
Run these test commands on the SCADA computer to confirm both external lookup links and local hardware names map cleanly:
```cmd
:: 1. Force a clean local lease refresh
ipconfig /release
ipconfig /renew

:: 2. Target the router directly to test DNS mapping resolution
nslookup labRTAC.labmon 192.168.88.1

:: 3. Test end-to-end communication by name mapping
ping labRTAC.labmon
ping api.pushover.net
```

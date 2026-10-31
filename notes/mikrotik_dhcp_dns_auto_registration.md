# MikroTik DHCP-to-DNS Automatic Registration Guide
**Target Devices:** 
* **Lab Router:** MikroTik RB5009UPr+S+IN (Subnet: `192.168.88.0/24`, Domain: `.labmon`)
* **Home Dev Router:** MikroTik L009UiGS-2HaxD (Subnet: `192.168.10.0/24`, Domain: `.lan`)

---

## 1. Overview
When industrial devices (PLCs, WAGO couplers, Raspberry Pis) connect via DHCP or have their leases made static in WinBox, MikroTik RouterOS does not automatically insert their hostname into `/ip dns static` unless this script is loaded.

With this configuration:
* Whenever a device claims a lease, renews, or is clicked **Make Static**, it automatically adds a DNS record with comment `DHCP Dynamic Lease`.
* Clients on the network can resolve `hostname` or `hostname.<domain>` immediately.

---

## 2. Configuration for Home Router (MikroTik L009)

### Step 1: Enable DNS Server for Local Clients
In WinBox:
1. Go to **IP** $\rightarrow$ **DNS**.
2. Check **Allow Remote Requests**.
3. Click **Apply** and **OK**.

*(CLI equivalent)*:
```routeros
/ip dns set allow-remote-requests=yes
```

---

### Step 2: Push Domain & DNS in DHCP Network
In WinBox:
1. Go to **IP** $\rightarrow$ **DHCP Server** $\rightarrow$ **Networks** tab.
2. Double-click your active subnet (e.g. `192.168.10.0/24`).
3. Set:
   * **DNS Servers:** `192.168.10.1` *(Your L009 LAN IP)*
   * **Domain:** `lan`
4. Click **Apply** and **OK**.

*(CLI equivalent)*:
```routeros
/ip dhcp-server network set [find address="192.168.10.0/24"] dns-server=192.168.10.1 domain="lan"
```

---

### Step 3: Install the Proven Auto-DNS Script
In WinBox:
1. Go to **IP** $\rightarrow$ **DHCP Server** $\rightarrow$ **DHCP** tab.
2. Double-click your DHCP server instance (usually `defconf` or `dhcp1`).
3. Click the **Script** tab (or find the **Lease Script** box).
4. Paste the following script:

```routeros
:local zone "lan"
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
5. Click **Apply** and **OK**.

---

## 3. Reference: Proven Lab Router Configuration (RB5009)

For completeness, here is the exact active configuration currently working on the lab RB5009:

* **Subnet:** `192.168.88.0/24`
* **Domain:** `labmon`
* **DNS Servers:** `192.168.88.1`
* **Script in DHCP Server:**
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

---

## 4. How to Use in Daily Operation (Single Place)

1. Connect your device (WAGO coupler, Raspberry Pi, laptop).
2. Open WinBox $\rightarrow$ **IP** $\rightarrow$ **DHCP Server** $\rightarrow$ **Leases** tab.
3. Right-click the newly discovered device and click **Make Static**.
4. Double-click the static lease:
   * Adjust the **Address** to your desired IP if needed.
   * If the device did not send a hostname, enter it in the **Host Name** field (or **Comment** field).
5. Click **OK**.
6. Open **IP** $\rightarrow$ **DNS** $\rightarrow$ **Static** tab: you will see the entry created automatically with comment `DHCP Dynamic Lease`!

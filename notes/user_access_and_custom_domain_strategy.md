# IVF Lab Telemetry: User Access, Authentication & Custom Domain Strategy

## 1. Executive Overview
This document defines the user access architecture, role-based security, and branding/domain configuration for the cloud-hosted IVF Lab SCADA Telemetry environment. 

The strategy balances two competing clinical requirements:
1. **Zero-friction access in the laboratory:** Technicians in sterile attire must be able to view live statuses and acknowledge alarms without typing passwords or completing 2-factor authentication prompts.
2. **Strict audit compliance & remote security:** Clinical staff, lab directors, and regulatory inspectors accessing telemetry off-site must have authenticated, role-scoped permissions that preserve an accountability audit trail.

---

## 2. User Access Tiers & Authentication Profiles

```
                      ┌─────────────────────────────────────────┐
                      │          Access Architecture            │
                      └────────────────────┬────────────────────┘
                                           │
         ┌─────────────────────────────────┼─────────────────────────────────┐
         │                                 │                                 │
         ▼                                 ▼                                 ▼
┌──────────────────┐             ┌───────────────────┐             ┌──────────────────┐
│  Tier 1: Kiosk   │             │   Tier 2: Staff   │             │ Tier 3: Auditor  │
│  (Wall Display)  │             │   (Mobile/Laptop) │             │ (Inspectors)     │
├──────────────────┤             ├───────────────────┤             ├──────────────────┤
│ • Zero login     │             │ • SSO (M365/Google│             │ • Scoped Viewer  │
│ • Kiosk mode     │             │ • Named accounts  │             │ • Read-only logs │
│ • Glove-friendly │             │ • Role: Viewer    │             │ • CSV export     │
└──────────────────┘             └───────────────────┘             └──────────────────┘
```

### Tier 1: Lab Wall Touchscreen Kiosk (Frictionless / In-Lab)
* **Target Device:** Wall-mounted touchscreen tablet or dedicated mini-PC monitor in the embryology suite.
* **Authentication Method:**
  * **Option A (Public Dashboard Link):** Enable the "Public Dashboard" feature on the IVF dashboard in Grafana Cloud. Generates a secure, view-only URL requiring zero credentials.
  * **Option B (Dedicated Device Service Account):** Create a dedicated device user (e.g., `kiosk-lab@clinic.com`) assigned the `Viewer` role. The device browser remains permanently logged in.
* **Kiosk Display Mode (`?kiosk`):**
  * Appending `?kiosk` to the URL strips all top navigation bars, side menus, and edit buttons.
  * The interface fills the display with high-contrast gauges, alarm cards, and trend graphs.
* **Tablet Hardening:** Configure the tablet OS (iPad Guided Access or Android Screen Pinning) with screen timeout set to "Never" and auto-relaunch on power cycle.

### Tier 2: Clinical Staff & Physicians (Named Remote Access)
* **Target Users:** Embryologists, Lab Directors, On-Call Physicians, Biomedical Engineers.
* **Role:** **`Viewer`**
  * Can view all real-time and historical dashboards.
  * Can adjust the time picker (e.g. "Last 24 hours", "Custom Date Range") and inspect telemetry.
  * **Restricted:** Cannot modify panel configurations, alter SQL queries, delete data, or view underlying database passwords.
* **Single Sign-On (SSO):**
  * Integration with clinic identity providers: **Microsoft 365 (Entra ID)** or **Google Workspace**.
  * Staff log in using their primary clinic email via "Sign in with Microsoft" or "Sign in with Google"—eliminating password sprawl and simplifying offboarding.
* **Accountability:** When staff submit alarm notes or acknowledge notifications, the system logs their exact name (e.g. `Dr. Sarah Jenkins`) rather than an anonymous entry.

### Tier 3: Regulatory Inspectors & Accreditation Auditors (CAP / CLIA)
* **Target Users:** College of American Pathologists (CAP), CLIA, Joint Commission, or state health surveyors.
* **Role:** Temporary **`Viewer`** account or supervised read-only session.
* **Permissions:** Ability to review historical temperature logs, thermal recovery graphs, and MTTA (Mean Time to Acknowledge) compliance reports with 1-click CSV data export.

---

## 3. Custom Domain & White-Label URL Strategy

Instead of directing staff to the default cloud endpoint (`https://steadypanda1446.grafana.net`), the system can be white-labeled under the clinic's primary domain (e.g., `yourclinic.com`).

### Architecture: CNAME DNS Mapping
```
Staff visits:                           Grafana Cloud resolves:
https://labmon.yourclinic.com  ─────►  steadypanda1446.grafana.net
                                        (SSL/TLS auto-provisioned)
```

### Option A: Custom Domain (CNAME Record)
1. In your domain registrar (GoDaddy, Cloudflare, Route53, Namecheap):
   * **Record Type:** `CNAME`
   * **Host / Subdomain:** `labmon` (or `scada`, `ivf-monitor`)
   * **Target:** `steadypanda1446.grafana.net`
   * **TTL:** Automatic or 300 seconds
2. In Grafana Cloud:
   * Map the custom domain in your Cloud Account settings.
   * Grafana automatically issues and renews an encrypted Let's Encrypt SSL/TLS certificate.
3. **Result:** Staff access the dashboard at:
   ```text
   https://labmon.yourclinic.com
   ```

### Option B: Cloudflare / Domain Forwarding (Lightweight & Free)
If using standard redirect rules without custom domain add-ons:
* Create a URL redirect rule in your domain host:
  * `https://lab.yourclinic.com` ──► `https://steadypanda1446.grafana.net/d/ivf-scada-main`
* Makes it effortless for staff to remember and bookmark on mobile browsers.

### Option C: Custom Dashboard URL Slugs
In Grafana dashboard settings, vanity paths can be defined so URLs are human-readable:
* Current: `/d/ivf-scada-main/ivf-clinical-lab-scada-telemetry`
* Clean slug: `/d/ivf-lab` or `/d/chamber-monitor`

---

## 4. Security, Privacy & HIPAA Considerations

1. **Zero PHI in Telemetry:**
   * Rapid SCADA and the PostgreSQL archive store purely physical parameters: temperatures, door open states, sensor health, and alarm flags.
   * **No Protected Health Information (PHI)** or patient identifiers exist within the SCADA telemetry stream, drastically reducing HIPAA compliance complexity.
2. **Reverse Tunnel Architecture (Zero Inbound Firewall Exposure):**
   * The Grafana PDC Agent initiates **outbound-only** connections from the Raspberry Pi on the private lab subnet.
   * The MikroTik router and corporate firewall require **no inbound port forwarding**.
   * Local PostgreSQL listens solely on `localhost:5432` and is shielded from the wider network.
3. **Scoped Database Credentials:**
   * Grafana Cloud connects exclusively through the `grafana_reader` role, restricted to `SELECT` permissions on `mod_arc_postgre_sql.*`.
   * It has no write, update, or schema alteration permissions on the database.

---

## 5. Summary Setup Checklist

| Step | Task | Status / Action |
| :--- | :--- | :--- |
| **1** | Configure Kiosk Touchscreen Display | Enable Public Dashboard link or save persistent session with `?kiosk` |
| **2** | Add Clinic CNAME in DNS | Add `CNAME labmon -> steadypanda1446.grafana.net` |
| **3** | Configure Clinic SSO | Connect Google Workspace or Microsoft 365 in Grafana Cloud |
| **4** | Invite Core Staff | Add lab staff with `Viewer` role for mobile/laptop monitoring |

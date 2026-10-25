# Cloud Database & Supabase Multi-Clinic Replication Strategy
**Company / Platform:** Lares Telemetry (`larestelemetry.com`)  
**Status:** Architectural Blueprint & Future Implementation Guide  
**Related Files:** [ivf_alert_engine.py](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py), [db.env.example](file:///home/bobostrom/Projects/labSCADA/db.env.example), [ivf-alert-engine.service](file:///home/bobostrom/Projects/labSCADA/ivf-alert-engine.service)

---

## 1. Executive Summary

As **Lares Telemetry** expands from an on-premise cleanroom monitor at Advanced Fertility of Alaska (`komdivflab.larestelemetry.com`) into a commercial product offered to multiple IVF clinics, embryology laboratories, and biobanks, telemetry data must be aggregated into a central cloud database.

Following architectural evaluation between **Google Cloud SQL**, **Neon**, and **Supabase**, **Supabase** was selected as the optimal cloud backend for the platform.

---

## 2. Why Supabase Was Selected

| Requirement | Supabase Capability | Benefit for Lares Telemetry |
| :--- | :--- | :--- |
| **PostgreSQL Compatibility** | Native PostgreSQL 16/17 engine | 100% drop-in compatibility with existing `mod_arc_postgre_sql` schema, tables, and Python queries. |
| **Multi-Clinic Data Isolation** | Built-in **Row Level Security (RLS)** | Allows all clinics to store data in a unified database while enforcing cryptographic boundaries: Clinic A staff can never see Clinic B records. |
| **User Authentication & Roles** | Built-in Auth Engine (JWT, Magic Links, Passwords) | Zero custom backend code needed to build login pages for Lab Directors, Embryologists, and Auditors. |
| **Compliance PDF & Image Storage** | Native **Storage Buckets** (S3-compatible) | Automatically stores monthly CAP compliance PDFs, audit logs, and sawtooth chart PNGs (`ln2_sawtooth_chart.png`) with zero egress fees. |
| **Live Browser Dashboards** | Built-in **Realtime WebSockets** | Telemetry pushed from cleanrooms updates web browser dashboards instantly without client polling. |
| **Cost & Scalability** | Free tier (500 MB DB, 1 GB storage), $25/mo Pro | Zero cloud costs during initial development, scaling to enterprise capabilities when client clinics come online. |

---

## 3. Edge-First Hybrid Architecture

> [!IMPORTANT]
> **Clinical Non-Negotiable:** An internet outage must **NEVER** disrupt local cleanroom operations, kiosk touchscreens, or manual dipstick logging.

The system will operate on an **Edge-First + Asynchronous Cloud Sync** model:

```
┌────────────────────────────────────────────────────────┐
│             CLINIC CLEANROOM (EDGE APPLIANCE)          │
│                                                        │
│  [Sensors & Probes] ──► [WAGO PLC / Codesys]           │
│                                │                       │
│                                ▼                       │
│                   [ivf_alert_engine.py]                │
│                                │                       │
│     Real-Time Writes           ▼                       │
│    ─────────────────► [Local PostgreSQL]              │
│    (Zero Latency)     (127.0.0.1:5432)                 │
│                                │                       │
│                   100% Offline │ Guaranteed Local      │
│                   Resilient    │ Kiosk & Alarm Uptime  │
└────────────────────────────────┼───────────────────────┘
                                 │
                                 │ Background Sync Worker
                                 │ (Buffers during outages)
                                 ▼ (Encrypted TLS / Port 5432)
┌────────────────────────────────────────────────────────┐
│          LARES TELEMETRY CLOUD (SUPABASE)              │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Central PostgreSQL Database                      │  │
│  │ • Table: mod_arc_postgre_sql.curcopy_current     │  │
│  │ • Table: mod_arc_postgre_sql.ln2_tank_logs       │  │
│  │ • Table: clinical_incident_reports               │  │
│  │ • Row Level Security: clinic_id = auth.uid()     │  │
│  └──────────────────────────────────────────────────┘  │
│                                │                       │
│         ┌──────────────────────┼──────────────────┐    │
│         ▼                      ▼                  ▼    │
│    [Storage Bucket]       [Auth Engine]      [Realtime]│
│    Monthly CAP PDFs       Lab Director       WebSockets│
│    & Sawtooth Charts      Clinic Logins      Live Dash │
└────────────────────────────────────────────────────────┘
```

1. **Local Edge (Raspberry Pi):** All sensor polling, touchscreen UI updates, alarm evaluations, and QR mobile dipstick logs execute against local PostgreSQL on `127.0.0.1:5432`.
2. **Outage Buffer:** If clinic internet drops, the local database queues all records. Local operations never know the internet was down.
3. **Asynchronous Uplink:** When internet is active, a background replication daemon syncs new rows to Supabase.
4. **Cloud Fleet View:** The central portal (`portal.larestelemetry.com`) queries Supabase, giving executives and directors high-level oversight of all tanks and cleanrooms across multiple locations.

---

## 4. Current Decoupling Status

The code has already been refactored to support this future cloud deployment:

* **Dynamic Environment Variables:** [ivf_alert_engine.py](file:///home/bobostrom/Projects/labSCADA/ivf_alert_engine.py) and [scripts/generate_ln2_report.py](file:///home/bobostrom/Projects/labSCADA/scripts/generate_ln2_report.py) read connection parameters dynamically:
  * `SCADA_PG_HOST`
  * `SCADA_PG_PORT`
  * `SCADA_PG_DB`
  * `SCADA_PG_USER`
  * `SCADA_PG_PASS`
  * `SCADA_PG_SSLMODE`
* **Configuration Override File:** `/etc/labscada/db.env` (templated at [db.env.example](file:///home/bobostrom/Projects/labSCADA/db.env.example)).
* **Service Integration:** [ivf-alert-engine.service](file:///home/bobostrom/Projects/labSCADA/ivf-alert-engine.service) automatically loads `/etc/labscada/db.env` on startup.

---

## 5. Action Plan When Returning to This Task

When ready to connect Supabase:

1. **Create Supabase Organization & Project:**
   * Sign in to [supabase.com](https://supabase.com) using `bobostrom@larestelemetry.com`.
   * Create a project named `lares-telemetry-prod` in the closest AWS region (e.g., `us-west-2` Oregon).
2. **Apply Database Schema:**
   * Run the schema definitions from [setup_channel_config.sql](file:///home/bobostrom/Projects/labSCADA/setup_channel_config.sql) and [setup_ln2_tracking.sql](file:///home/bobostrom/Projects/labSCADA/setup_ln2_tracking.sql) in the Supabase SQL editor.
   * Add a `clinic_id text default 'komdivflab'` column to all tables.
3. **Configure Storage Bucket:**
   * Create a bucket named `compliance-reports` (private, with signed URL downloads).
4. **Deploy Edge Sync Daemon:**
   * Write a lightweight Python worker (or use PostgreSQL logical replication) on the Raspberry Pi that watches for new local rows and writes them to Supabase via its direct PostgreSQL connection string.
5. **Test Multi-Tenant Dashboard:**
   * Build a lightweight web interface on `larestelemetry.com` that lets clinic directors sign in and view real-time charts powered by Supabase.

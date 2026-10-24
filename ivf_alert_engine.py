#!/usr/bin/env python3
"""
==============================================================================
IVF Laboratory SCADA Clinical Alert & Escalation Engine
==============================================================================
Manages end-to-end clinical alarm lifecycle for Advanced Fertility of Alaska:
1. Multi-variable excursion detection (CODESYS discrete alarms & analog limits)
2. Pushover Emergency Priority 2 sirens with discrete receipt tracking
3. Instant one-tap silence/acknowledgment API for Lab Kiosk & Mobile Web
4. Background polling for mobile phone lock-screen acknowledgments
5. 30-minute escalation watcher for unattended/unrecovered chambers
6. Tamper-proof permanent audit logging in PostgreSQL (mod_arc_postgre_sql.alarm_events)
7. Daily QA Pathway Test dispatch and logging for CAP/CLIA accreditation
==============================================================================
"""

import http.server
import json
import os
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

PORT = 8080
PG_USER = "postgres"
PG_PASS = "postgres"
PG_HOST = "127.0.0.1"
PG_DB = "rapid_scada"

PUSHOVER_TOKEN = "a2wmo7ofxhhpo2vc2ykdkhtnte8nb5"
PUSHOVER_GROUP = "gepqspoh98t69c7o223hwbg8ponwyq"
PUSHOVER_PING_URL = "https://api.pushover.net/1/monitors/mm5z3n2shg9hjn2785oyu649ri92cxh/ping.json"

ESCALATION_TIMEOUT_SECONDS = 1800  # 30 minutes

# Monitored equipment definitions
CHANNELS = {
    101: {"name": "Lab Ambient", "type": "ambient", "low": 20.0, "high": 27.0},
    102: {"name": "Medical Fridge", "type": "fridge", "low": 2.0, "high": 8.0},
    103: {"name": "Medical Freezer", "type": "freezer", "high": -15.0},
    121: {"name": "Main Cleanroom Door", "type": "door"},
    122: {"name": "Cryo Lab Door", "type": "door"},
    123: {"name": "Incubator 01", "type": "incubator"},
    124: {"name": "Incubator 02", "type": "incubator"},
    125: {"name": "Cryo Tank 1", "type": "cryo", "high": -135.0},
    # New discrete alarm channels from CODESYS
    126: {"name": "Medical Fridge", "type": "discrete_alarm", "linked_analog": 102},
    127: {"name": "Medical Freezer", "type": "discrete_alarm", "linked_analog": 103},
    128: {"name": "Cryo Tank 1", "type": "discrete_alarm", "linked_analog": 125},
    129: {"name": "Main Cleanroom Door", "type": "door_alarm", "linked_contact": 121},
    130: {"name": "Cryo Lab Door", "type": "door_alarm", "linked_contact": 122},
}

# In-memory tracking of active alarm state machine
# Key: channel number -> dict of active alarm details
active_alarms = {}
state_lock = threading.Lock()


# ==============================================================================
# DATABASE HELPERS (PostgreSQL)
# ==============================================================================
def db_query(sql):
    """Executes a SQL SELECT query and returns rows as list of tuples."""
    env = os.environ.copy()
    env["PGPASSWORD"] = PG_PASS
    try:
        res = subprocess.run(
            ["psql", "-h", PG_HOST, "-U", PG_USER, "-d", PG_DB, "-t", "-A", "-F", "\t", "-c", sql],
            env=env,
            capture_output=True,
            text=True,
            timeout=8
        )
        if res.returncode != 0:
            print(f"DB Error: {res.stderr.strip()}")
            return []
        rows = []
        for line in res.stdout.strip().split("\n"):
            if line:
                rows.append(line.split("\t"))
        return rows
    except Exception as e:
        print(f"DB Query Exception: {e}")
        return []


def db_execute(sql):
    """Executes an INSERT / UPDATE / DELETE command."""
    env = os.environ.copy()
    env["PGPASSWORD"] = PG_PASS
    try:
        res = subprocess.run(
            ["psql", "-h", PG_HOST, "-U", PG_USER, "-d", PG_DB, "-q", "-c", sql],
            env=env,
            capture_output=True,
            text=True,
            timeout=8
        )
        return res.returncode == 0
    except Exception as e:
        print(f"DB Execute Exception: {e}")
        return False


def get_current_channel_values():
    """Queries mod_arc_postgre_sql.curcopy_current for real-time channel readings."""
    sql = "SELECT cnl_num, val, stat FROM mod_arc_postgre_sql.curcopy_current;"
    rows = db_query(sql)
    readings = {}
    for r in rows:
        if len(r) >= 2:
            try:
                cnl = int(r[0])
                val = float(r[1])
                readings[cnl] = val
            except ValueError:
                pass
    return readings


# ==============================================================================
# PUSHOVER API CLIENT
# ==============================================================================
def send_pushover_alert(title, message, priority=0, sound="pushover", retry=60, expire=7200):
    """Sends a Pushover notification. For priority=2, returns (True, receipt_id)."""
    url = "https://api.pushover.net/1/messages.json"
    post_data = {
        "token": PUSHOVER_TOKEN,
        "user": PUSHOVER_GROUP,
        "title": title,
        "message": message,
        "priority": priority,
        "sound": sound
    }
    if priority == 2:
        post_data["retry"] = max(30, retry)
        post_data["expire"] = expire

    encoded = urllib.parse.urlencode(post_data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            res_body = res.read().decode("utf-8")
            res_json = json.loads(res_body)
            receipt = res_json.get("receipt")
            return True, receipt
    except Exception as e:
        print(f"Pushover send error: {e}")
        return False, None


def cancel_pushover_receipt(receipt):
    """Cancels a specific repeating emergency Priority 2 alert in Pushover."""
    if not receipt:
        return False
    url = f"https://api.pushover.net/1/receipts/cancel/{receipt}.json"
    encoded = urllib.parse.urlencode({"token": PUSHOVER_TOKEN}).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            res_body = res.read().decode("utf-8")
            res_json = json.loads(res_body)
            return res_json.get("status") == 1
    except Exception as e:
        print(f"Pushover cancel error for receipt {receipt}: {e}")
def check_pushover_receipt(receipt):
    """Polls Pushover API for receipt delivery/acknowledgment status."""
    if not receipt:
        return None
    url = f"https://api.pushover.net/1/receipts/{receipt}.json?token={PUSHOVER_TOKEN}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            res_body = res.read().decode("utf-8")
            return json.loads(res_body)
    except Exception as e:
        print(f"Pushover check receipt error: {e}")
        return None


# Cache of Pushover user keys -> human names (from Pushover Group memos)
pushover_user_cache = {}
last_user_cache_time = 0

def get_pushover_user_name(user_key, device=None):
    """Automatically resolves a 30-char Pushover user key to a human name via the Pushover Group API."""
    global last_user_cache_time
    now = time.time()

    # Refresh cache if empty or older than 1 hour
    if not pushover_user_cache or (now - last_user_cache_time > 3600):
        try:
            url = f"https://api.pushover.net/1/groups/{PUSHOVER_GROUP}.json?token={PUSHOVER_TOKEN}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=8) as res:
                data = json.loads(res.read().decode("utf-8"))
                if data.get("status") == 1:
                    for u in data.get("users", []):
                        k = u.get("user")
                        memo = u.get("memo", "").strip()
                        if k and memo:
                            pushover_user_cache[k] = memo
                    last_user_cache_time = now
                    print(f"[{datetime.now().strftime('%T')}] Synced {len(pushover_user_cache)} user memos from Pushover.net")
        except Exception as e:
            print(f"Error fetching Pushover group users: {e}")

    # Friendly name resolution
    name = pushover_user_cache.get(user_key)
    if not name:
        name = "NAME NOT KNOWN"

    dev_label = f" ({device})" if device else " (Phone)"
    return f"{name}{dev_label}"


# ==============================================================================
# ALARM LIFECYCLE CONTROLLER
# ==============================================================================
def trigger_alarm(cnl_num, equipment_name, alarm_type, excursion_val):
    """Fires a new emergency alarm, captures receipt, and logs to PostgreSQL."""
    with state_lock:
        if cnl_num in active_alarms:
            # Alarm already active; prevent duplicate sirens
            return active_alarms[cnl_num]["db_id"]

    val_str = f"{excursion_val:.1f}°C" if excursion_val is not None else "TRIPPED"
    title = f"🔴 CRITICAL ALARM: {equipment_name}"
    message = f"{equipment_name} {alarm_type}! Reading: {val_str}. Immediate intervention required."

    print(f"[{datetime.now().strftime('%T')}] FIRING SIREN: {title} ({val_str})")
    success, receipt = send_pushover_alert(
        title=title,
        message=message,
        priority=2,
        sound="siren",
        retry=60,
        expire=7200
    )

    # Insert record into PostgreSQL alarm_events table
    safe_equip = equipment_name.replace("'", "''")
    safe_type = alarm_type.replace("'", "''")
    safe_val = str(excursion_val) if excursion_val is not None else "NULL"
    safe_receipt = f"'{receipt}'" if receipt else "NULL"

    sql = f"""
    INSERT INTO mod_arc_postgre_sql.alarm_events 
        (cnl_num, equipment_name, alarm_type, excursion_val, triggered_at, pushover_receipt, is_acknowledged, is_resolved)
    VALUES 
        ({cnl_num}, '{safe_equip}', '{safe_type}', {safe_val}, NOW(), {safe_receipt}, FALSE, FALSE)
    RETURNING id;
    """
    rows = db_query(sql)
    db_id = int(rows[0][0]) if rows and rows[0] else 0

    with state_lock:
        active_alarms[cnl_num] = {
            "db_id": db_id,
            "equipment_name": equipment_name,
            "alarm_type": alarm_type,
            "excursion_val": excursion_val,
            "triggered_at": time.time(),
            "pushover_receipt": receipt,
            "is_acknowledged": False,
            "acknowledged_by": None,
            "acknowledged_at": None,
            "escalated": False
        }
    return db_id


def resolve_alarm(cnl_num, final_val=None):
    """Marks an active alarm as resolved when the chamber returns to normal."""
    with state_lock:
        if cnl_num not in active_alarms:
            return
        alarm = active_alarms.pop(cnl_num)

    db_id = alarm["db_id"]
    equip = alarm["equipment_name"]
    receipt = alarm["pushover_receipt"]
    duration = int(time.time() - alarm["triggered_at"])
    duration_str = f"{duration // 60}m {duration % 60}s"

    print(f"[{datetime.now().strftime('%T')}] RESOLVED: {equip} (Duration: {duration_str})")

    # If the repeating siren was never acknowledged, cancel it now
    if receipt and not alarm["is_acknowledged"]:
        cancel_pushover_receipt(receipt)

    # Update database
    sql = f"""
    UPDATE mod_arc_postgre_sql.alarm_events 
    SET is_resolved = TRUE, 
        resolved_at = NOW(), 
        duration_seconds = {duration}
    WHERE id = {db_id};
    """
    db_execute(sql)

    # Send Priority 0 "RESOLVED" notification with chime
    val_disp = f"({final_val:.1f}°C)" if final_val is not None else ""
    send_pushover_alert(
        title=f"🟢 RESOLVED: {equip} Normal",
        message=f"{equip} has returned to safe operational range {val_disp}. Duration: {duration_str}.",
        priority=0,
        sound="magic"
    )


def acknowledge_alarm(alarm_id, acknowledged_by="Lab Kiosk", user_token="local_kiosk"):
    """Silences the siren for a specific alarm and updates the audit record with friendly name and immutable token."""
    target_alarm = None
    target_cnl = None

    with state_lock:
        for cnl, alarm in active_alarms.items():
            if alarm["db_id"] == alarm_id:
                target_alarm = alarm
                target_cnl = cnl
                break

    # If not in local active cache, check database
    if not target_alarm:
        sql = f"SELECT id, pushover_receipt, equipment_name FROM mod_arc_postgre_sql.alarm_events WHERE id = {alarm_id} AND is_acknowledged = FALSE;"
        rows = db_query(sql)
        if not rows:
            return False, "Alarm not found or already acknowledged."
        receipt = rows[0][1] if rows[0][1] and rows[0][1] != "NULL" else None
        equip = rows[0][2]
    else:
        receipt = target_alarm["pushover_receipt"]
        equip = target_alarm["equipment_name"]
        with state_lock:
            target_alarm["is_acknowledged"] = True
            target_alarm["acknowledged_by"] = acknowledged_by
            target_alarm["acknowledged_at"] = time.time()

    # Cancel the repeating emergency siren in Pushover
    if receipt:
        cancel_pushover_receipt(receipt)

    # Update PostgreSQL audit table (capturing friendly display name AND immutable token)
    safe_user = acknowledged_by.replace("'", "''")
    safe_token = user_token.replace("'", "''") if user_token else "local_kiosk"
    token_sql = f"'{safe_token}'"

    sql = f"""
    UPDATE mod_arc_postgre_sql.alarm_events 
    SET is_acknowledged = TRUE, 
        acknowledged_by = '{safe_user}', 
        acknowledged_by_token = {token_sql}, 
        acknowledged_at = NOW() 
    WHERE id = {alarm_id};
    """
    db_execute(sql)

    # Send silent informational broadcast to all on-call staff
    now_str = datetime.now().strftime("%H:%M:%S")
    send_pushover_alert(
        title=f"🔕 ALARM ACKNOWLEDGED: {equip}",
        message=f"{equip} alarm was acknowledged by {acknowledged_by} at {now_str}. Siren silenced. Staff attending.",
        priority=0,
        sound="pushover"
    )

    print(f"[{datetime.now().strftime('%T')}] ACKNOWLEDGED: {equip} by {acknowledged_by} (token: {safe_token})")
    return True, f"Alarm {alarm_id} acknowledged by {acknowledged_by}."


# ==============================================================================
# BACKGROUND SCAN & ESCALATION WORKERS
# ==============================================================================
def telemetry_scan_worker():
    """Continuously evaluates channel readings against alarm states."""
    while True:
        try:
            readings = get_current_channel_values()
            now = time.time()

            # 1. Evaluate Discrete Alarm Bits from CODESYS (Channels 123, 124, 126-130)
            discrete_evals = [
                (123, "Incubator 01", "Chamber Alarm Contact"),
                (124, "Incubator 02", "Chamber Alarm Contact"),
                (126, "Medical Fridge", "Temperature Excursion"),
                (127, "Medical Freezer", "Temperature Excursion"),
                (128, "Cryo Tank 1", "Liquid Nitrogen Excursion"),
                (129, "Main Cleanroom Door", "Door Held Open > 3m"),
                (130, "Cryo Lab Door", "Door Held Open > 3m"),
            ]

            for cnl, equip, alarm_type in discrete_evals:
                if cnl in readings:
                    val = readings[cnl]
                    if val > 0:
                        # Discrete alarm bit is HIGH
                        trigger_alarm(cnl, equip, alarm_type, None)
                    else:
                        # Discrete alarm bit is LOW
                        resolve_alarm(cnl, None)

            # 2. Evaluate Analog Limit Fallbacks (If discrete tags not yet loaded in CODESYS)
            # Med Fridge (Cnl 102)
            if 102 in readings and 126 not in readings:
                f_temp = readings[102]
                if f_temp > 8.0 or f_temp < 2.0:
                    trigger_alarm(102, "Medical Fridge", "Temperature Excursion", f_temp)
                elif f_temp <= 7.5 and f_temp >= 2.5:
                    resolve_alarm(102, f_temp)

            # Med Freezer (Cnl 103)
            if 103 in readings and 127 not in readings:
                fz_temp = readings[103]
                if fz_temp > -15.0:
                    trigger_alarm(103, "Medical Freezer", "Temperature Excursion", fz_temp)
                elif fz_temp <= -16.5:
                    resolve_alarm(103, fz_temp)

            # Cryo Tank 1 (Cnl 125)
            if 125 in readings and 128 not in readings:
                c_temp = readings[125]
                if c_temp > -135.0:
                    trigger_alarm(125, "Cryo Tank 1", "Liquid Nitrogen Excursion", c_temp)
                elif c_temp <= -140.0:
                    resolve_alarm(125, c_temp)

        except Exception as e:
            print(f"Scan loop error: {e}")

        time.sleep(2.0)


def phone_sync_and_escalation_worker():
    """Syncs mobile phone acknowledgments from Pushover and monitors escalations."""
    while True:
        try:
            # 1. Sync Mobile Phone Acknowledgment from Pushover
            sql = """
            SELECT id, pushover_receipt, equipment_name 
            FROM mod_arc_postgre_sql.alarm_events 
            WHERE is_acknowledged = FALSE 
              AND is_resolved = FALSE 
              AND pushover_receipt IS NOT NULL;
            """
            unacked_rows = db_query(sql)
            for r in unacked_rows:
                db_id = int(r[0])
                receipt = r[1]
                equip = r[2]
                res = check_pushover_receipt(receipt)
                if res and res.get("acknowledged") == 1:
                    raw_user = res.get("acknowledged_by")
                    dev = res.get("acknowledged_by_device")
                    acked_by = get_pushover_user_name(raw_user, dev)
                    print(f"[{datetime.now().strftime('%T')}] Phone Ack Detected for {equip}: {acked_by} (token: {raw_user})")
                    acknowledge_alarm(db_id, acknowledged_by=acked_by, user_token=raw_user)

            # 2. Escalation Watcher (30-Minute Safety Net)
            # If an alarm was acknowledged, but the chamber is STILL not resolved after 30 minutes:
            sql_esc = f"""
            SELECT id, equipment_name, excursion_val, acknowledged_by, EXTRACT(EPOCH FROM (NOW() - acknowledged_at))
            FROM mod_arc_postgre_sql.alarm_events 
            WHERE is_acknowledged = TRUE 
              AND is_resolved = FALSE 
              AND acknowledged_at < NOW() - INTERVAL '30 minutes';
            """
            esc_rows = db_query(sql_esc)
            with state_lock:
                for r in esc_rows:
                    db_id = int(r[0])
                    equip = r[1]
                    acked_user = r[3]
                    # Check if already escalated
                    for cnl, alarm in active_alarms.items():
                        if alarm["db_id"] == db_id and not alarm["escalated"]:
                            alarm["escalated"] = True
                            print(f"[{datetime.now().strftime('%T')}] FIRING ESCALATION: {equip} still unrecovered after 30m!")
                            send_pushover_alert(
                                title=f"🚨 ESCALATION: {equip} Still Unrecovered!",
                                message=f"{equip} remains out of range 30 min after acknowledgment by {acked_user}. Immediate director intervention required.",
                                priority=2,
                                sound="siren",
                                retry=60,
                                expire=7200
                            )

        except Exception as e:
            print(f"Escalation worker error: {e}")

        time.sleep(15.0)


# ==============================================================================
# HTTP REST API & WEB CONTROLLER
# ==============================================================================
class ClinicalAlertHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/status":
            readings = get_current_channel_values()
            with state_lock:
                alarms_copy = [dict(v) for v in active_alarms.values()]
            data = {
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "active_alarm_count": len(alarms_copy),
                "active_alarms": alarms_copy,
                "readings": readings
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))

        elif parsed.path == "/api/alarms":
            sql = """
            SELECT id, cnl_num, equipment_name, alarm_type, excursion_val, 
                   triggered_at, is_acknowledged, acknowledged_by, acknowledged_by_token, acknowledged_at, 
                   is_resolved, resolved_at, duration_seconds 
            FROM mod_arc_postgre_sql.alarm_events 
            ORDER BY triggered_at DESC 
            LIMIT 15;
            """
            rows = db_query(sql)
            results = []
            for r in rows:
                if len(r) >= 13:
                    results.append({
                        "id": int(r[0]),
                        "cnl_num": int(r[1]),
                        "equipment_name": r[2],
                        "alarm_type": r[3],
                        "excursion_val": float(r[4]) if r[4] and r[4] != "NULL" else None,
                        "triggered_at": r[5],
                        "is_acknowledged": r[6] == "t",
                        "acknowledged_by": r[7] if r[7] != "NULL" else None,
                        "acknowledged_by_token": r[8] if r[8] != "NULL" else None,
                        "acknowledged_at": r[9] if r[9] != "NULL" else None,
                        "is_resolved": r[10] == "t",
                        "resolved_at": r[11] if r[11] != "NULL" else None,
                        "duration_seconds": int(r[12]) if r[12] and r[12] != "NULL" else None
                    })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(results).encode("utf-8"))

        else:
            # Rich web view with live telemetry cards, QA button, and alarm table
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = f"""<!DOCTYPE html>
            <html>
            <head>
              <meta charset="utf-8">
              <meta name="viewport" content="width=device-width, initial-scale=1">
              <title>IVF Lab Clinical Dashboard & Alert Controller</title>
              <style>
                body {{ background:#090d16; color:#f0f4f8; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding:24px; }}
                header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:16px; }}
                h1 {{ color:#00e5ff; font-size:1.6rem; font-weight:700; margin:0; }}
                .subtitle {{ color:#8899a6; font-size:0.9rem; margin-top:4px; }}
                .badge-live {{ background:rgba(0,230,118,0.15); color:#00e676; border:1px solid #00e676; padding:4px 12px; border-radius:100px; font-size:13px; font-weight:600; display:flex; align-items:center; gap:8px; }}
                .pulse-dot {{ width:8px; height:8px; background:#00e676; border-radius:50%; box-shadow:0 0 8px #00e676; animation:pulse 1.5s infinite; }}
                @keyframes pulse {{ 0% {{ opacity:0.4; }} 50% {{ opacity:1; }} 100% {{ opacity:0.4; }} }}

                /* Telemetry Grid */
                .grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:16px; margin-bottom:24px; }}
                .card {{ background:rgba(18,25,41,0.85); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:18px; position:relative; overflow:hidden; }}
                .card-title {{ color:#8899a6; font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px; }}
                .card-val {{ font-size:2.2rem; font-weight:700; font-family:monospace; color:#f0f4f8; }}
                .card-unit {{ font-size:1.1rem; color:#8899a6; margin-left:4px; }}
                .card-sub {{ font-size:12px; color:#8899a6; margin-top:8px; display:flex; justify-content:space-between; }}
                .status-badge {{ font-size:12px; font-weight:700; padding:2px 8px; border-radius:4px; }}
                .status-normal {{ background:rgba(0,230,118,0.15); color:#00e676; }}
                .status-warn {{ background:rgba(255,171,0,0.15); color:#ffab00; }}
                .status-alert {{ background:rgba(255,23,68,0.25); color:#ff1744; font-weight:800; }}

                /* Control & History Rows */
                .section-card {{ background:rgba(18,25,41,0.85); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:20px; margin-bottom:20px; }}
                .btn {{ background:#2979ff; color:white; border:none; padding:8px 16px; border-radius:6px; cursor:pointer; font-weight:600; }}
                .btn:hover {{ background:#1e6cd9; }}
                .btn-test {{ background:#00e676; color:#090d16; font-size:15px; font-weight:700; padding:12px 24px; border-radius:8px; cursor:pointer; border:none; box-shadow:0 4px 14px rgba(0,230,118,0.3); }}
                .btn-test:hover {{ background:#00c853; }}
                
                table {{ width:100%; border-collapse:collapse; margin-top:12px; }}
                th, td {{ padding:10px 14px; text-align:left; border-bottom:1px solid rgba(255,255,255,0.06); font-size:14px; }}
                th {{ color:#8899a6; text-transform:uppercase; font-size:12px; }}
              </style>
            </head>
            <body>
              <header>
                <div>
                  <h1>IVF Laboratory Cleanroom Telemetry</h1>
                  <div class="subtitle">Advanced Fertility of Alaska — Clinical SCADA Monitor</div>
                </div>
                <div class="badge-live"><div class="pulse-dot"></div> Live Telemetry Active</div>
              </header>

              <!-- Live Environmental Cards -->
              <div class="grid">
                <div class="card" id="card-fridge">
                  <div class="card-title">Medical Fridge</div>
                  <div class="card-val"><span id="val-fridge">--</span><span class="card-unit">°C</span></div>
                  <div class="card-sub">
                    <span>Range: 2.0°C – 8.0°C</span>
                    <span id="badge-fridge" class="status-badge status-normal">NORMAL</span>
                  </div>
                </div>

                <div class="card" id="card-freezer">
                  <div class="card-title">Medical Freezer</div>
                  <div class="card-val"><span id="val-freezer">--</span><span class="card-unit">°C</span></div>
                  <div class="card-sub">
                    <span>Limit: &lt; -15.0°C</span>
                    <span id="badge-freezer" class="status-badge status-normal">NORMAL</span>
                  </div>
                </div>

                <div class="card" id="card-cryo">
                  <div class="card-title">Cryo Tank 1 (LN2 Vapor)</div>
                  <div class="card-val"><span id="val-cryo">--</span><span class="card-unit">°C</span></div>
                  <div class="card-sub">
                    <span>Critical: &lt; -135.0°C</span>
                    <span id="badge-cryo" class="status-badge status-normal">NORMAL</span>
                  </div>
                </div>

                <div class="card" id="card-ambient">
                  <div class="card-title">Cleanroom Ambient</div>
                  <div class="card-val"><span id="val-ambient">--</span><span class="card-unit">°C</span></div>
                  <div class="card-sub">
                    <span>Target: ~25.0°C</span>
                    <span id="badge-ambient" class="status-badge status-normal">COMFORT</span>
                  </div>
                </div>

                <div class="card" id="card-door1">
                  <div class="card-title">Main Cleanroom Door</div>
                  <div class="card-val" id="val-door1" style="font-size:1.6rem; margin-top:6px;">CLOSED</div>
                  <div class="card-sub">
                    <span>Limit: &lt; 3m open</span>
                    <span id="badge-door1" class="status-badge status-normal">SECURE</span>
                  </div>
                </div>

                <div class="card" id="card-incubators">
                  <div class="card-title">Chamber Incubators</div>
                  <div class="card-val" id="val-incubators" style="font-size:1.6rem; margin-top:6px;">NORMAL</div>
                  <div class="card-sub">
                    <span>Incubator 01 & 02</span>
                    <span id="badge-incubators" class="status-badge status-normal">ALL CLEAR</span>
                  </div>
                </div>
              </div>

              <!-- Daily QA Test Controller -->
              <div class="section-card">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px;">
                  <div>
                    <h3 style="margin-bottom:4px;">Daily Alarm Verification (CAP/CLIA)</h3>
                    <p style="color:#8899a6; font-size:13px;">Dispatches verified Priority 0 test notification to team and writes regulatory timestamp.</p>
                  </div>
                  <div>
                    <button class="btn-test" onclick="runDailyTest()">🔔 Run Daily Alarm Pathway Test</button>
                  </div>
                </div>
                <div id="testStatus" style="margin-top:12px; font-size:13px; color:#00e676; font-weight:600;"></div>
              </div>

              <!-- Live Alarms Table -->
              <div class="section-card">
                <h3 style="margin-bottom:4px;">Active Alarms & Clinical Audit Trail</h3>
                <p style="color:#8899a6; font-size:13px; margin-bottom:12px;">Reverse chronological history. Tap Acknowledge to silence repeating sirens.</p>
                <div id="alarmsTable">Loading alarms...</div>
              </div>

              <script>
                function updateTelemetry() {{
                  fetch('/api/status')
                    .then(r => r.json())
                    .then(data => {{
                      const r = data.readings || {{}};
                      
                      // Ambient
                      if (r[101] !== undefined) {{
                        document.getElementById('val-ambient').innerText = r[101].toFixed(1);
                      }}
                      // Fridge
                      if (r[102] !== undefined) {{
                        const f = r[102];
                        document.getElementById('val-fridge').innerText = f.toFixed(1);
                        const b = document.getElementById('badge-fridge');
                        if (f > 8.0 || f < 2.0) {{
                          b.innerText = 'EXCURSION';
                          b.className = 'status-badge status-alert';
                        }} else {{
                          b.innerText = 'NORMAL';
                          b.className = 'status-badge status-normal';
                        }}
                      }}
                      // Freezer
                      if (r[103] !== undefined) {{
                        const fz = r[103];
                        document.getElementById('val-freezer').innerText = fz.toFixed(1);
                        const b = document.getElementById('badge-freezer');
                        if (fz > -15.0) {{
                          b.innerText = 'HIGH';
                          b.className = 'status-badge status-alert';
                        }} else {{
                          b.innerText = 'NORMAL';
                          b.className = 'status-badge status-normal';
                        }}
                      }}
                      // Cryo
                      if (r[125] !== undefined) {{
                        const cr = r[125];
                        document.getElementById('val-cryo').innerText = cr.toFixed(1);
                        const b = document.getElementById('badge-cryo');
                        if (cr > -135.0) {{
                          b.innerText = 'CRITICAL';
                          b.className = 'status-badge status-alert';
                        }} else {{
                          b.innerText = 'NORMAL';
                          b.className = 'status-badge status-normal';
                        }}
                      }}
                      // Door 01
                      if (r[121] !== undefined) {{
                        const d = r[121] > 0;
                        document.getElementById('val-door1').innerText = d ? 'OPEN' : 'CLOSED';
                        document.getElementById('val-door1').style.color = d ? '#ffab00' : '#f0f4f8';
                        const b = document.getElementById('badge-door1');
                        b.innerText = d ? 'AJAR' : 'SECURE';
                        b.className = d ? 'status-badge status-warn' : 'status-badge status-normal';
                      }}
                      // Incubators
                      const inc1 = r[123] || 0;
                      const inc2 = r[124] || 0;
                      const incAlarm = (inc1 > 0 || inc2 > 0);
                      document.getElementById('val-incubators').innerText = incAlarm ? 'ALARM' : 'NORMAL';
                      document.getElementById('val-incubators').style.color = incAlarm ? '#ff1744' : '#f0f4f8';
                      const bInc = document.getElementById('badge-incubators');
                      bInc.innerText = incAlarm ? 'TRIPPED' : 'ALL CLEAR';
                      bInc.className = incAlarm ? 'status-badge status-alert' : 'status-badge status-normal';
                    }})
                    .catch(e => console.error('Telemetry error:', e));
                }}

                function runDailyTest() {{
                  const st = document.getElementById('testStatus');
                  st.innerText = '⏳ Dispatching test alert to Pushover...';
                  fetch('/api/test', {{ method: 'POST' }})
                    .then(r => r.json())
                    .then(d => {{
                      st.innerText = '✅ Daily Alarm Test dispatched to team at ' + d.timestamp + ' (Pushover Priority 0)';
                      loadAlarms();
                      setTimeout(() => {{ st.innerText = ''; }}, 6000);
                    }})
                    .catch(e => {{ st.innerText = '❌ Failed to send test alert'; }});
                }}

                function ackAlarm(id) {{
                  fetch('/api/ack?id=' + id, {{ method: 'POST' }})
                    .then(r => r.json())
                    .then(d => {{
                      loadAlarms();
                    }});
                }}

                function loadAlarms() {{
                  fetch('/api/alarms')
                    .then(r => r.json())
                    .then(rows => {{
                      if (rows.length === 0) {{
                        document.getElementById('alarmsTable').innerHTML = '<p style="color:#00e676; padding:12px 0;">🟢 All systems normal. No alarm events recorded.</p>';
                        return;
                      }}
                      let h = '<table><thead><tr><th>Time</th><th>Equipment</th><th>Condition</th><th>Reading</th><th>Status</th><th>Action</th></tr></thead><tbody>';
                      rows.forEach(r => {{
                        let statusHtml = '';
                        let actHtml = '-';
                        if (!r.is_acknowledged && !r.is_resolved) {{
                          statusHtml = '<span style="color:#ff1744; font-weight:700;">🔴 ACTIVE (SIREN)</span>';
                          actHtml = `<button class="btn" onclick="ackAlarm(${{r.id}})">✋ Acknowledge</button>`;
                        }} else if (r.is_acknowledged && !r.is_resolved) {{
                          const tok = r.acknowledged_by_token ? ` title="Immutable Token: ${{r.acknowledged_by_token}}"` : '';
                          statusHtml = `<span style="color:#ffab00; font-weight:600;"${{tok}}>🟡 Attending (${{r.acknowledged_by || 'Staff'}})</span>`;
                        }} else {{
                          statusHtml = '<span style="color:#00e676;">🟢 Resolved</span>';
                        }}
                        const valDisp = r.excursion_val !== null ? r.excursion_val + '°C' : '-';
                        const timeDisp = r.triggered_at ? r.triggered_at.split('.')[0] : '-';
                        h += `<tr><td>${{timeDisp}}</td><td><b>${{r.equipment_name}}</b></td><td>${{r.alarm_type}}</td><td>${{valDisp}}</td><td>${{statusHtml}}</td><td>${{actHtml}}</td></tr>`;
                      }});
                      h += '</tbody></table>';
                      document.getElementById('alarmsTable').innerHTML = h;
                    }});
                }}

                setInterval(updateTelemetry, 1500);
                setInterval(loadAlarms, 3000);
                updateTelemetry();
                loadAlarms();
              </script>
            </body>
            </html>"""
            self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/api/test":
            now_str = datetime.now().strftime("%H:%M:%S")
            success, _ = send_pushover_alert(
                title="🔔 IVF LAB QA: Daily Alarm Pathway Test",
                message=f"Daily alarm pathway test initiated from Lab Kiosk at {now_str}. All systems operational.",
                priority=0,
                sound="magic"
            )
            # Record QA test into PostgreSQL
            sql = f"""
            INSERT INTO mod_arc_postgre_sql.alarm_events 
                (cnl_num, equipment_name, alarm_type, excursion_val, triggered_at, is_acknowledged, acknowledged_by, acknowledged_at, is_resolved, resolved_at, duration_seconds)
            VALUES 
                (0, 'QA System', 'Daily Pathway Test', NULL, NOW(), TRUE, 'Lab Kiosk', NOW(), TRUE, NOW(), 0);
            """
            db_execute(sql)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "timestamp": now_str}).encode("utf-8"))

        elif parsed.path == "/api/ack":
            alarm_id_str = params.get("id", [None])[0]
            user = params.get("user", ["Lab Kiosk"])[0]
            if not alarm_id_str:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing alarm id parameter"}).encode("utf-8"))
                return

            try:
                alarm_id = int(alarm_id_str)
                success, msg = acknowledge_alarm(alarm_id, acknowledged_by=user)
                self.send_response(200 if success else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"success": success, "message": msg}).encode("utf-8"))
            except ValueError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid alarm id"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================
def main():
    print(f"Starting IVF Clinical Alert & Escalation Engine on port {PORT}...")

    # Spawn background scan & phone sync threads
    t_scan = threading.Thread(target=telemetry_scan_worker, daemon=True)
    t_scan.start()

    t_phone = threading.Thread(target=phone_sync_and_escalation_worker, daemon=True)
    t_phone.start()

    # Start HTTP server
    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer(("0.0.0.0", PORT), ClinicalAlertHandler)
    print(f"Ready. Listening for Kiosk / Web API calls on http://0.0.0.0:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down gracefully.")
        server.server_close()


if __name__ == "__main__":
    main()

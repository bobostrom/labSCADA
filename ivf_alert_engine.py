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
from datetime import datetime, timedelta

import jinja2

try:
    import qrcode
    import qrcode.image.svg
    QR_ENABLED = True
except ImportError:
    QR_ENABLED = False

PORT = 8080
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(REPO_DIR, "templates")

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES_DIR),
    autoescape=jinja2.select_autoescape(["html", "xml"])
)

def render_template(template_name, **context):
    """Renders a Jinja2 template from the templates directory."""
    template = jinja_env.get_template(template_name)
    return template.render(**context)

def load_env_file(filepath):
    """Loads key=value pairs from a file into os.environ if file exists."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            print(f"Warning: could not load env file {filepath}: {e}")

# Check system-wide config first, then local repo .env
load_env_file("/etc/labscada/db.env")
load_env_file(os.path.join(REPO_DIR, ".env"))

PG_USER = os.environ.get("SCADA_PG_USER", os.environ.get("PGUSER", "postgres"))
PG_PASS = os.environ.get("SCADA_PG_PASS", os.environ.get("PGPASSWORD", "postgres"))
PG_HOST = os.environ.get("SCADA_PG_HOST", os.environ.get("PGHOST", "127.0.0.1"))
PG_PORT = os.environ.get("SCADA_PG_PORT", os.environ.get("PGPORT", "5432"))
PG_DB   = os.environ.get("SCADA_PG_DB",   os.environ.get("PGDATABASE", "rapid_scada"))
PG_SSLMODE = os.environ.get("SCADA_PG_SSLMODE", os.environ.get("PGSSLMODE", "prefer"))

PUSHOVER_TOKEN = "a2wmo7ofxhhpo2vc2ykdkhtnte8nb5"
PUSHOVER_GROUP = "gepqspoh98t69c7o223hwbg8ponwyq"
PUSHOVER_PING_URL = "https://api.pushover.net/1/monitors/mm5z3n2shg9hjn2785oyu649ri92cxh/ping.json"

ESCALATION_TIMEOUT_SECONDS = 1800  # 30 minutes

# Monitored equipment definitions with explicit alarm priorities:
# Priority 2: Critical Specimen Life-Safety (Repeating siren, 30m escalation)
# Priority 1: Operational & Compliance Warnings (One-shot notice, 8:00 AM morning sweep, no siren)
CHANNELS = {
    101: {"name": "Lab Ambient", "type": "ambient", "low": 20.0, "high": 27.0, "priority": 1},
    102: {"name": "Medical Fridge", "type": "fridge", "low": 2.0, "high": 8.0, "priority": 2},
    103: {"name": "Medical Freezer", "type": "freezer", "high": -15.0, "priority": 2},
    104: {"name": "Cryo Tank 2", "type": "cryo", "high": -135.0, "priority": 2},
    125: {"name": "Cryo Tank 1", "type": "cryo", "high": -135.0, "priority": 2},
    # Discrete alarm channels from CODESYS
    111: {"name": "Medical Fridge", "type": "discrete_alarm", "linked_analog": 102, "priority": 2},
    112: {"name": "Medical Freezer", "type": "discrete_alarm", "linked_analog": 103, "priority": 2},
    113: {"name": "Cryo Tank 1", "type": "discrete_alarm", "linked_analog": 125, "priority": 2},
    114: {"name": "Cryo Tank 2", "type": "discrete_alarm", "linked_analog": 104, "priority": 2},
    115: {"name": "Medical Fridge Warning", "type": "warning_delay", "linked_analog": 102, "priority": 0},
    116: {"name": "Medical Freezer Warning", "type": "warning_delay", "linked_analog": 103, "priority": 0},
    117: {"name": "Cryo Tank 1 Warning", "type": "warning_delay", "linked_analog": 125, "priority": 0},
    118: {"name": "Cryo Tank 2 Warning", "type": "warning_delay", "linked_analog": 104, "priority": 0},
    119: {"name": "Main Cleanroom Door Contact", "type": "door_contact", "priority": 0},
    120: {"name": "Cryo Lab Door Contact", "type": "door_contact", "priority": 0},
    121: {"name": "Main Cleanroom Door", "type": "door_alarm", "priority": 2},
    122: {"name": "Cryo Lab Door", "type": "door_alarm", "priority": 2},
    123: {"name": "Incubator 01", "type": "incubator", "priority": 2},
    124: {"name": "Incubator 02", "type": "incubator", "priority": 2},
    198: {"name": "Cryo Tank 2", "type": "ln2_inspection", "schedule": "Mon, Wed, Fri by 5:00 PM", "priority": 1},
    199: {"name": "Cryo Tank 1", "type": "ln2_inspection", "schedule": "Mon, Wed, Fri by 5:00 PM", "priority": 1},
}

# In-memory tracking of active alarm state machine
active_alarms = {}
state_lock = threading.Lock()
last_morning_sweep_date = ""


# ==============================================================================
# DATABASE HELPERS (PostgreSQL)
# ==============================================================================
def db_query(sql):
    """Executes a SQL SELECT query and returns rows as list of tuples."""
    env = os.environ.copy()
    env["PGPASSWORD"] = PG_PASS
    if PG_SSLMODE:
        env["PGSSLMODE"] = PG_SSLMODE
    try:
        res = subprocess.run(
            ["psql", "-h", PG_HOST, "-p", str(PG_PORT), "-U", PG_USER, "-d", PG_DB, "-t", "-A", "-F", "\t", "-c", sql],
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
    if PG_SSLMODE:
        env["PGSSLMODE"] = PG_SSLMODE
    try:
        res = subprocess.run(
            ["psql", "-h", PG_HOST, "-p", str(PG_PORT), "-U", PG_USER, "-d", PG_DB, "-q", "-c", sql],
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
    url = f"https://api.pushover.net/1/receipts/{receipt}/cancel.json"
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
def trigger_alarm(cnl_num, equipment_name, alarm_type, excursion_val, priority=None):
    """Fires an alarm according to priority tier (P2 Emergency Siren or P1 Compliance Notice)."""
    with state_lock:
        if cnl_num in active_alarms:
            # Alarm already active; prevent duplicate sirens/alerts
            return active_alarms[cnl_num]["db_id"]

    if priority is None:
        cfg = CHANNELS.get(cnl_num, {})
        priority = cfg.get("priority", 2)

    val_str = f"{excursion_val:.1f}°C" if excursion_val is not None else "TRIPPED"
    if cnl_num in (198, 199) and excursion_val is not None:
        val_str = f"{excursion_val:.1f}h since check"

    if priority == 2:
        title = f"🔴 CRITICAL ALARM: {equipment_name}"
        message = f"{equipment_name} {alarm_type}! Reading: {val_str}. Immediate intervention required."
        sound = "siren"
        print(f"[{datetime.now().strftime('%T')}] FIRING EMERGENCY SIREN (Priority 2): {title} ({val_str})")
        success, receipt = send_pushover_alert(
            title=title,
            message=message,
            priority=2,
            sound=sound,
            retry=60,
            expire=7200
        )
    else:  # Priority 1: High-priority warning (single alert, no repeating siren)
        title = f"⚠️ COMPLIANCE WARNING: {equipment_name}"
        message = f"{equipment_name}: {alarm_type}. Please attend to this during cleanroom operations."
        sound = "intermission"
        print(f"[{datetime.now().strftime('%T')}] DISPATCHING WARNING (Priority 1): {title}")
        success, receipt = send_pushover_alert(
            title=title,
            message=message,
            priority=1,
            sound=sound
        )

    # Insert record into PostgreSQL alarm_events table
    safe_equip = equipment_name.replace("'", "''")
    safe_type = alarm_type.replace("'", "''")
    safe_val = str(excursion_val) if excursion_val is not None else "NULL"
    safe_receipt = f"'{receipt}'" if receipt else "NULL"

    sql = f"""
    INSERT INTO mod_arc_postgre_sql.alarm_events 
        (cnl_num, equipment_name, alarm_type, excursion_val, triggered_at, pushover_receipt, is_acknowledged, is_resolved, priority)
    VALUES 
        ({cnl_num}, '{safe_equip}', '{safe_type}', {safe_val}, NOW(), {safe_receipt}, FALSE, FALSE, {priority})
    RETURNING id;
    """
    rows = db_query(sql)
    db_id = int(rows[0][0]) if rows and rows[0] else 0

    with state_lock:
        active_alarms[cnl_num] = {
            "db_id": db_id,
            "cnl_num": cnl_num,
            "equipment_name": equipment_name,
            "alarm_type": alarm_type,
            "excursion_val": excursion_val,
            "priority": priority,
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

    # Under Option 1 (Forced Wake-Up Policy):
    # Do NOT cancel the Pushover repeating siren upon physical recovery.
    # The siren continues repeating every 60s and the 'Acknowledge' button remains
    # active on staff phones until an authorized person acknowledges on phone or kiosk.

    # Update database
    sql = f"""
    UPDATE mod_arc_postgre_sql.alarm_events 
    SET is_resolved = TRUE, 
        resolved_at = NOW(), 
        duration_seconds = {duration}
    WHERE id = {db_id};
    """
    db_execute(sql)

    # Send Priority 0 "RECOVERED" notification with chime
    val_disp = f"({final_val:.1f} cm)" if (cnl_num in (198, 199) and final_val is not None) else (f"({final_val:.1f}°C)" if final_val is not None else "")
    send_pushover_alert(
        title=f"🟢 RECOVERED: {equip} Normal",
        message=f"{equip} has returned to safe operational range {val_disp}. Duration: {duration_str}. Siren will continue repeating until acknowledged on phone or kiosk.",
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

            # 1. Evaluate Discrete Alarm Bits from CODESYS (Channels 111-114, 121-124)
            discrete_evals = [
                (111, "Medical Fridge", "Temperature Excursion"),
                (112, "Medical Freezer", "Temperature Excursion"),
                (113, "Cryo Tank 1", "Liquid Nitrogen Excursion"),
                (114, "Cryo Tank 2", "Liquid Nitrogen Excursion"),
                (121, "Main Cleanroom Door", "Door Held Open > 3m"),
                (122, "Cryo Lab Door", "Door Held Open > 3m"),
                (123, "Incubator 01", "Chamber Alarm Contact"),
                (124, "Incubator 02", "Chamber Alarm Contact"),
            ]

            for cnl, equip, alarm_type in discrete_evals:
                if cnl in readings:
                    val = readings[cnl]
                    linked = CHANNELS.get(cnl, {}).get("linked_analog")
                    analog_val = readings.get(linked) if linked else None
                    if val > 0:
                        # Discrete alarm bit is HIGH
                        trigger_alarm(cnl, equip, alarm_type, analog_val)
                    else:
                        # Discrete alarm bit is LOW
                        resolve_alarm(cnl, analog_val)

            # 2. Evaluate Analog Limit Fallbacks (If discrete alarm channels not present)
            # Med Fridge (Cnl 102)
            if 102 in readings and 111 not in readings:
                f_temp = readings[102]
                if f_temp > 8.5 or f_temp < 2.0:
                    trigger_alarm(102, "Medical Fridge", "Temperature Excursion", f_temp)
                elif f_temp <= 7.5 and f_temp >= 2.5:
                    resolve_alarm(102, f_temp)

            # Med Freezer (Cnl 103)
            if 103 in readings and 112 not in readings:
                fz_temp = readings[103]
                if fz_temp > -15.0:
                    trigger_alarm(103, "Medical Freezer", "Temperature Excursion", fz_temp)
                elif fz_temp <= -16.5:
                    resolve_alarm(103, fz_temp)

            # Cryo Tank 1 (Cnl 125)
            if 125 in readings and 113 not in readings:
                c_temp = readings[125]
                if c_temp > -135.0:
                    trigger_alarm(125, "Cryo Tank 1", "Liquid Nitrogen Excursion", c_temp)
                elif c_temp <= -140.0:
                    resolve_alarm(125, c_temp)

            # Cryo Tank 2 (Cnl 104)
            if 104 in readings and 114 not in readings:
                c2_temp = readings[104]
                if c2_temp > -135.0:
                    trigger_alarm(104, "Cryo Tank 2", "Liquid Nitrogen Excursion", c2_temp)
                elif c2_temp <= -140.0:
                    resolve_alarm(104, c2_temp)

        except Exception as e:
            print(f"Scan loop error: {e}")

        time.sleep(1.0)


def phone_sync_and_escalation_worker():
    """Syncs mobile phone acknowledgments from Pushover and monitors escalations."""
    while True:
        try:
            # 1. Sync Mobile Phone Acknowledgment from Pushover (both active and recovered alarms)
            sql = """
            SELECT id, pushover_receipt, equipment_name 
            FROM mod_arc_postgre_sql.alarm_events 
            WHERE is_acknowledged = FALSE 
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

            # 2. Escalation Watcher (30-Minute Safety Net for Priority 2 Alarms Only)
            # If a Critical Priority 2 alarm was acknowledged, but the chamber is STILL not resolved after 30 minutes:
            sql_esc = f"""
            SELECT id, equipment_name, excursion_val, acknowledged_by, EXTRACT(EPOCH FROM (NOW() - acknowledged_at))
            FROM mod_arc_postgre_sql.alarm_events 
            WHERE is_acknowledged = TRUE 
              AND is_resolved = FALSE 
              AND priority = 2
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
                        if alarm["db_id"] == db_id and not alarm["escalated"] and alarm.get("priority", 2) == 2:
                            alarm["escalated"] = True
                            print(f"[{datetime.now().strftime('%T')}] FIRING ESCALATION (P2): {equip} still unrecovered after 30m!")
                            send_pushover_alert(
                                title=f"🚨 ESCALATION: {equip} Still Unrecovered!",
                                message=f"{equip} remains out of range 30 min after acknowledgment by {acked_user}. Immediate director intervention required.",
                                priority=2,
                                sound="siren",
                                retry=60,
                                expire=7200
                            )

            # 3. 8:00 AM Morning Shift Sweep (Daily check for active Priority 1 Compliance Warnings)
            global last_morning_sweep_date
            now_dt = datetime.now()
            today_str = now_dt.strftime("%Y-%m-%d")
            if now_dt.hour == 8 and last_morning_sweep_date != today_str:
                with state_lock:
                    p1_active = [a for a in active_alarms.values() if a.get("priority") == 1]
                if p1_active:
                    equip_names = ", ".join(sorted(list(set(a["equipment_name"] for a in p1_active))))
                    print(f"[{datetime.now().strftime('%T')}] 🌅 DISPATCHING 8:00 AM MORNING SWEEP for: {equip_names}")
                    send_pushover_alert(
                        title="🌅 MORNING ROUNDS: Pending Compliance Items",
                        message=f"Morning shift sweep detected pending item(s) for: {equip_names}. Please complete inspections at cleanroom kiosk.",
                        priority=1,
                        sound="intermission"
                    )
                last_morning_sweep_date = today_str

        except Exception as e:
            print(f"Escalation worker error: {e}")

        # Poll faster (5s) if there are active unacknowledged sirens, otherwise 15s
        has_unacked = False
        try:
            has_unacked = len(unacked_rows) > 0
        except Exception:
            pass
        time.sleep(5.0 if has_unacked else 15.0)


# ==============================================================================
# LIQUID NITROGEN (LN2) MON / WED / FRI 5:00 PM MANUAL INSPECTION TRACKER
# ==============================================================================
def evaluate_ln2_schedule(now, last_log_time, initials="--", level_cm=0.0):
    """
    Evaluates LN2 compliance for cleanroom Mon / Wed / Fri schedule (due by 5:00 PM).
    """
    SCHEDULE_DAYS = [0, 2, 4]  # 0=Monday, 2=Wednesday, 4=Friday
    CUTOFF_HOUR = 17           # 5:00 PM

    # 1. Determine last passed deadline
    if now.weekday() in SCHEDULE_DAYS and now.hour >= CUTOFF_HOUR:
        last_deadline_date = now.date()
    else:
        last_deadline_date = now.date() - timedelta(days=1)
        while last_deadline_date.weekday() not in SCHEDULE_DAYS:
            last_deadline_date -= timedelta(days=1)

    last_deadline_day_start = datetime(last_deadline_date.year, last_deadline_date.month, last_deadline_date.day, 0, 0, 0)

    # 2. Check if last deadline was satisfied
    is_last_satisfied = (last_log_time is not None and last_log_time >= last_deadline_day_start)

    # 3. Next upcoming deadline
    today_due = (now.weekday() in SCHEDULE_DAYS and now.hour < CUTOFF_HOUR)
    logged_today = (last_log_time is not None and last_log_time >= datetime(now.year, now.month, now.day, 0, 0, 0))

    if today_due and not logged_today:
        next_deadline_date = now.date()
    else:
        next_deadline_date = now.date() + timedelta(days=1)
        while next_deadline_date.weekday() not in SCHEDULE_DAYS:
            next_deadline_date += timedelta(days=1)

    next_check_str = f"{next_deadline_date.strftime('%A (%b %-d)')} by 5:00 PM"

    if level_cm is not None and 0.0 < level_cm < 27.0:
        return {
            "status": "OVERDUE",
            "badge": "CRITICAL LEVEL",
            "detail": f"🔴 CRITICAL: Level {level_cm:.1f} cm (< 27.0 cm floor)! Accelerated boil-off / vacuum loss.",
            "next_check": next_check_str
        }

    if not is_last_satisfied:
        return {
            "status": "OVERDUE",
            "badge": "OVERDUE",
            "detail": f"🔴 OVERDUE: {last_deadline_date.strftime('%A')} check was required by 5:00 PM!",
            "next_check": next_check_str
        }

    if today_due:
        if logged_today:
            return {
                "status": "NORMAL",
                "badge": "COMPLETED",
                "detail": f"🟢 COMPLETED: Today's check logged by {initials} ({level_cm:.1f} cm). Next check: {next_check_str}",
                "next_check": next_check_str
            }
        else:
            return {
                "status": "DUE",
                "badge": "DUE TODAY",
                "detail": f"🟡 DUE TODAY: {now.strftime('%A')} dipstick check due by 5:00 PM.",
                "next_check": next_check_str
            }
    else:
        return {
            "status": "NORMAL",
            "badge": "ON SCHEDULE",
            "detail": f"🟢 ON SCHEDULE: Next check: {next_check_str}",
            "next_check": next_check_str
        }


def get_ln2_status():
    """Returns latest inspection status and recent logs for all cryo tanks based on Mon/Wed/Fri 5pm schedule."""
    sql = """
    SELECT DISTINCT ON (tank_id) 
        tank_id, level_cm, was_filled, frost_condition, initials, notes, 
        logged_at,
        ROUND(EXTRACT(EPOCH FROM (NOW() - logged_at)) / 3600.0, 1) AS hours_since
    FROM mod_arc_postgre_sql.ln2_tank_logs
    ORDER BY tank_id, logged_at DESC;
    """
    rows = db_query(sql)
    tanks = {}
    now = datetime.now()
    for r in rows:
        if len(r) >= 8:
            t_id = r[0]
            lvl = float(r[1]) if r[1] else 0.0
            filled = (r[2] == "t")
            frost = r[3]
            initials = r[4]
            notes = r[5] if r[5] != "NULL" else ""
            ts = r[6]
            hours_since = float(r[7]) if r[7] else 0.0

            log_dt = None
            if ts:
                try:
                    clean_ts = ts[:19]
                    log_dt = datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

            sched = evaluate_ln2_schedule(now, log_dt, initials=initials, level_cm=lvl)

            tanks[t_id] = {
                "tank_id": t_id,
                "level_cm": lvl,
                "was_filled": filled,
                "frost_condition": frost,
                "initials": initials,
                "notes": notes,
                "logged_at": ts,
                "hours_since": hours_since,
                "status": sched["status"],
                "badge": sched["badge"],
                "detail": sched["detail"],
                "next_check": sched["next_check"]
            }

    # Ensure both tanks have baseline representation
    for expected_tank in ["Cryo Tank 1", "Cryo Tank 2"]:
        if expected_tank not in tanks:
            sched_def = evaluate_ln2_schedule(now, None)
            tanks[expected_tank] = {
                "tank_id": expected_tank,
                "level_cm": 0.0,
                "was_filled": False,
                "frost_condition": "Good",
                "initials": "--",
                "notes": "No logs recorded yet",
                "logged_at": None,
                "hours_since": 0.0,
                "status": sched_def["status"],
                "badge": sched_def["badge"],
                "detail": sched_def["detail"],
                "next_check": sched_def["next_check"]
            }

    # Also fetch recent 10 history rows
    sql_hist = """
    SELECT id, tank_id, level_cm, was_filled, frost_condition, initials, notes, logged_at
    FROM mod_arc_postgre_sql.ln2_tank_logs
    ORDER BY logged_at DESC
    LIMIT 10;
    """
    hist_rows = db_query(sql_hist)
    history = []
    for r in hist_rows:
        if len(r) >= 8:
            history.append({
                "id": int(r[0]),
                "tank_id": r[1],
                "level_cm": float(r[2]),
                "was_filled": (r[3] == "t"),
                "frost_condition": r[4],
                "initials": r[5],
                "notes": r[6] if r[6] != "NULL" else "",
                "logged_at": r[7]
            })
    return {"tanks": tanks, "history": history}


def record_ln2_log(tank_id, level_cm, was_filled, frost_condition, initials, notes=""):
    """Inserts a new dipstick inspection log and satisfies current schedule requirement."""
    safe_tank = tank_id.replace("'", "''")
    safe_frost = frost_condition.replace("'", "''")
    safe_init = initials.strip().upper().replace("'", "''")
    safe_notes = notes.replace("'", "''")

    sql = f"""
    INSERT INTO mod_arc_postgre_sql.ln2_tank_logs 
        (tank_id, level_cm, was_filled, frost_condition, initials, notes, logged_at)
    VALUES 
        ('{safe_tank}', {level_cm:.2f}, {str(was_filled).upper()}, '{safe_frost}', '{safe_init}', '{safe_notes}', NOW())
    RETURNING id;
    """
    rows = db_query(sql)
    log_id = int(rows[0][0]) if rows and rows[0] else 0

    # Resolve overdue alarm for this specific tank (199 for Tank 1, 198 for Tank 2)
    alarm_cnl = 199 if safe_tank == "Cryo Tank 1" else 198
    with state_lock:
        if alarm_cnl in active_alarms:
            resolve_alarm(alarm_cnl, final_val=level_cm)

    # Determine next due date for notification
    status_info = get_ln2_status()
    t_info = status_info.get("tanks", {}).get(safe_tank, {})
    next_due_msg = t_info.get("next_check", "Next Mon/Wed/Fri by 5:00 PM")

    # Send informational notification to team via Pushover
    filled_str = "Yes (Tank Topped Off)" if was_filled else "No (Level Check Only)"
    send_pushover_alert(
        title=f"🧊 LN2 LOGGED: {safe_tank} ({level_cm:.1f} cm)",
        message=f"{safe_tank} inspected by {safe_init}. Level: {level_cm:.1f} cm. Filled: {filled_str}. Seal: {safe_frost}. Next check: {next_due_msg}.",
        priority=0,
        sound="magic"
    )
    print(f"[{datetime.now().strftime('%T')}] LN2 Log Recorded for {safe_tank}: {level_cm} cm by {safe_init} (Filled: {was_filled}). Next check: {next_due_msg}")
    return log_id


def ln2_schedule_watcher():
    """Background loop verifying that LN2 tanks are inspected per Mon/Wed/Fri 5:00 PM schedule."""
    while True:
        try:
            status_data = get_ln2_status()
            tanks = status_data.get("tanks", {})
            tank_cnls = [("Cryo Tank 1", 199), ("Cryo Tank 2", 198)]
            for tank_name, cnl_num in tank_cnls:
                tank = tanks.get(tank_name)
                if tank:
                    status = tank.get("status")
                    detail = tank.get("detail", f"{tank_name} Manual Check Overdue")
                    if status == "OVERDUE":
                        with state_lock:
                            already_active = cnl_num in active_alarms
                        if not already_active:
                            print(f"[{datetime.now().strftime('%T')}] LN2 INSPECTION OVERDUE: {tank_name} ({detail})")
                            trigger_alarm(
                                cnl_num=cnl_num,
                                equipment_name=tank_name,
                                alarm_type=detail,
                                excursion_val=round(tank.get("hours_since", 0.0), 1),
                                priority=1
                            )
                    else:
                        with state_lock:
                            if cnl_num in active_alarms:
                                resolve_alarm(cnl_num, final_val=tank["level_cm"])
        except Exception as e:
            print(f"LN2 schedule watcher error: {e}")
        time.sleep(60.0)


# ==============================================================================
# QR CODE PLACARD & MOBILE ENTRY GENERATORS
# ==============================================================================
def generate_qr_svg(url, box_size=8):
    """Generates an inline SVG QR code string for the given URL."""
    if not QR_ENABLED:
        return f'<svg width="180" height="180" viewBox="0 0 180 180" xmlns="http://www.w3.org/2000/svg"><rect width="180" height="180" fill="#f1f5f9"/><text x="15" y="95" fill="#475569" font-family="sans-serif" font-size="12">python3-qrcode required</text></svg>'
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(url, image_factory=factory, box_size=box_size, border=2)
    raw = img.to_string()
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


def render_print_placards_html(host, scheme="http"):
    """Generates a high-resolution, printable 8.5x11 single station placard with a vector QR code for both cryo tanks."""
    station_url = f"{scheme}://{host}/log"
    qr_svg = generate_qr_svg(station_url, box_size=9)
    return render_template("station_placard.html", station_url=station_url, qr_svg=qr_svg)


def render_mobile_log_html(host, tank_param, readings):
    """Renders a responsive, mobile-first dipstick entry interface for staff scanning QR codes with their phone."""
    is_tank2 = "2" in str(tank_param)
    default_tank = "Cryo Tank 2" if is_tank2 else "Cryo Tank 1"
    
    t1_temp = readings.get(125, readings.get(113, -196.2))
    t1_level = readings.get(199, 14.5)
    t2_temp = readings.get(104, readings.get(114, -196.0))
    t2_level = readings.get(198, 16.8)

    disp_temp = f"{t2_temp if is_tank2 else t1_temp:.1f} °C"
    disp_sensor = f"{t2_level if is_tank2 else t1_level:.1f} cm"
    init_level = f"{t2_level if is_tank2 else t1_level:.1f}"

    return render_template(
        "mobile_log.html",
        is_tank2=is_tank2,
        default_tank=default_tank,
        disp_temp=disp_temp,
        disp_sensor=disp_sensor,
        init_level=init_level,
        t1_temp_disp=f"{t1_temp:.1f} °C",
        t1_level_disp=f"{t1_level:.1f} cm",
        t1_default_val=f"{t1_level:.1f}",
        t2_temp_disp=f"{t2_temp:.1f} °C",
        t2_level_disp=f"{t2_level:.1f} cm",
        t2_default_val=f"{t2_level:.1f}"
    )


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

            # Last Daily QA Test Status
            qa_rows = db_query("SELECT triggered_at, acknowledged_by FROM mod_arc_postgre_sql.alarm_events WHERE equipment_name = 'QA System' ORDER BY triggered_at DESC LIMIT 1;")
            last_qa = None
            if qa_rows and qa_rows[0]:
                last_qa = {
                    "triggered_at": str(qa_rows[0][0]),
                    "by": str(qa_rows[0][1])
                }

            data = {
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "active_alarm_count": len(alarms_copy),
                "active_alarms": alarms_copy,
                "readings": readings,
                "last_qa": last_qa
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
                   is_resolved, resolved_at, duration_seconds, priority 
            FROM mod_arc_postgre_sql.alarm_events 
            ORDER BY triggered_at DESC 
            LIMIT 15;
            """
            rows = db_query(sql)
            results = []
            for r in rows:
                if len(r) >= 13:
                    p = int(r[13]) if len(r) >= 14 and r[13] and r[13] != "NULL" else 2
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
                        "duration_seconds": int(r[12]) if r[12] and r[12] != "NULL" else None,
                        "priority": p
                    })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(results).encode("utf-8"))

        elif parsed.path == "/api/ln2_status":
            data = get_ln2_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))

        elif parsed.path in ["/report/ln2", "/reports/ln2"]:
            params = urllib.parse.parse_qs(parsed.query)
            month_param = params.get("month", [None])[0]
            if not month_param:
                month_param = datetime.now().strftime("%Y-%m")
            
            script_path = os.path.join(REPO_DIR, "scripts", "generate_ln2_report.py")
            report_packet_path = os.path.join(REPO_DIR, "notes", "ln2_monthly_compliance_packet.html")

            # Always generate fresh on-demand for requested month (stateless, zero accumulated files)
            try:
                subprocess.run(["python3", script_path, "--month", month_param], check=True)
            except Exception as e:
                print(f"Error generating monthly report packet for {month_param}: {e}")

            if os.path.exists(report_packet_path):
                with open(report_packet_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Report not found.")

        elif parsed.path == "/report/ln2/md":
            params = urllib.parse.parse_qs(parsed.query)
            tank_param = params.get("tank", ["1"])[0]
            suffix = "tank2" if "2" in str(tank_param) else "tank1"
            report_md_path = os.path.join(REPO_DIR, "notes", f"ln2_dipstick_compliance_report_{suffix}.md")
            if not os.path.exists(report_md_path):
                report_md_path = os.path.join(REPO_DIR, "notes", "ln2_dipstick_compliance_report.md")
            if os.path.exists(report_md_path):
                with open(report_md_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Markdown report not found.")

        elif parsed.path == "/favicon.ico":
            asset_path = os.path.join(REPO_DIR, "notes", "assets", "favicon.ico")
            if not os.path.exists(asset_path):
                asset_path = os.path.join(REPO_DIR, "notes", "assets", "KOMDlogo.png")
            if os.path.exists(asset_path):
                with open(asset_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/x-icon")
                self.send_header("Cache-Control", "no-cache, must-revalidate")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Favicon not found.")

        elif parsed.path.startswith("/assets/") or parsed.path.startswith("/notes/assets/"):
            filename = os.path.basename(parsed.path)
            asset_path = os.path.join(REPO_DIR, "assets", filename)
            if not os.path.exists(asset_path):
                asset_path = os.path.join(REPO_DIR, "notes", "assets", filename)
            if os.path.exists(asset_path) and os.path.isfile(asset_path):
                content_type = "image/x-icon" if filename.endswith(".ico") else ("image/png" if filename.endswith(".png") else ("image/svg+xml" if filename.endswith(".svg") else "application/octet-stream"))
                with open(asset_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Asset not found.")

        elif parsed.path in ["/report/ln2/chart", "/assets/ln2_sawtooth_chart.png", "/notes/assets/ln2_sawtooth_chart.png"]:
            params = urllib.parse.parse_qs(parsed.query)
            tank_param = params.get("tank", ["1"])[0]
            suffix = "tank2" if "2" in str(tank_param) else "tank1"
            tank_num = "2" if "2" in str(tank_param) else "1"
            chart_path = os.path.join(REPO_DIR, "assets", f"ln2_sawtooth_cryo_tank_{tank_num}.png")
            if not os.path.exists(chart_path):
                chart_path = os.path.join(REPO_DIR, "assets", f"ln2_sawtooth_chart_{suffix}.png")
            if not os.path.exists(chart_path):
                chart_path = os.path.join(REPO_DIR, "assets", "ln2_sawtooth_chart.png")
            if not os.path.exists(chart_path):
                chart_path = os.path.join(REPO_DIR, "notes", "assets", f"ln2_sawtooth_cryo_tank_{tank_num}.png")
            if os.path.exists(chart_path):
                with open(chart_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Chart not found.")
        elif parsed.path in ["/print/qr", "/qr"]:
            host = self.headers.get("Host", "192.168.10.133")
            scheme = "https" if ("larestelemetry.com" in host or "trycloudflare.com" in host or self.headers.get("X-Forwarded-Proto") == "https" or "https" in self.headers.get("CF-Visitor", "")) else "http"
            html = render_print_placards_html(host, scheme=scheme)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path in ["/log", "/ln2_log"]:
            params = urllib.parse.parse_qs(parsed.query)
            tank_param = params.get("tank", ["1"])[0]
            host = self.headers.get("Host", "192.168.10.133")
            readings = get_current_channel_values()
            html = render_mobile_log_html(host, tank_param, readings)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path in ["/qr/station.svg", "/qr.svg", "/qr/tank1.svg", "/qr/tank2.svg"]:
            tank_num = "2" if "tank2" in parsed.path else ("1" if "tank1" in parsed.path else None)
            host = self.headers.get("Host", "192.168.10.133")
            scheme = "https" if ("larestelemetry.com" in host or "trycloudflare.com" in host or self.headers.get("X-Forwarded-Proto") == "https" or "https" in self.headers.get("CF-Visitor", "")) else "http"
            if tank_num:
                target_url = f"{scheme}://{host}/log?tank={tank_num}"
            else:
                target_url = f"{scheme}://{host}/log"
            svg_data = generate_qr_svg(target_url, box_size=8)
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(svg_data.encode("utf-8"))

        else:
            # Rich Cleanroom Kiosk Touchscreen View
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = render_template("kiosk.html")
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

        elif parsed.path == "/api/ln2_log":
            content_length = int(self.headers.get("Content-Length", 0))
            body_str = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
            payload = {}
            if body_str:
                try:
                    payload = json.loads(body_str)
                except Exception:
                    raw_qs = urllib.parse.parse_qs(body_str)
                    payload = {k: v[0] for k, v in raw_qs.items()}

            tank_id = payload.get("tank_id") or params.get("tank_id", ["Cryo Tank 1"])[0]
            level_str = payload.get("level_cm") or params.get("level_cm", [None])[0]
            was_filled_val = payload.get("was_filled") or params.get("was_filled", ["false"])[0]
            was_filled = str(was_filled_val).lower() in ("true", "1", "yes", "t")
            frost = payload.get("frost_condition") or params.get("frost_condition", ["Good"])[0]
            initials = payload.get("initials") or params.get("initials", [""])[0]
            notes = payload.get("notes") or params.get("notes", [""])[0]

            if not level_str or not initials.strip():
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "level_cm and initials are required"}).encode("utf-8"))
                return

            try:
                level_cm = float(level_str)
                log_id = record_ln2_log(tank_id, level_cm, was_filled, frost, initials, notes)

                # Automatically regenerate compliance report in background so charts stay up to date
                try:
                    threading.Thread(
                        target=lambda: subprocess.run(["python3", os.path.join(REPO_DIR, "scripts", "generate_ln2_report.py")], check=False),
                        daemon=True
                    ).start()
                except Exception as _re:
                    pass

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True,
                    "log_id": log_id,
                    "message": f"Recorded {level_cm:.1f} cm for {tank_id} by {initials.upper()}."
                }).encode("utf-8"))
            except ValueError:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid level_cm value"}).encode("utf-8"))

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

    t_ln2 = threading.Thread(target=ln2_schedule_watcher, daemon=True)
    t_ln2.start()

    # Start HTTP server
    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer(("0.0.0.0", PORT), ClinicalAlertHandler)
    print(f"Connected to database at {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DB} (sslmode={PG_SSLMODE})")
    print(f"Ready. Listening for Kiosk / Web API calls on http://0.0.0.0:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down gracefully.")
        server.server_close()


if __name__ == "__main__":
    main()

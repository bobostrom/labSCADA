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

PORT = 8080
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
PG_USER = "postgres"
PG_PASS = "postgres"
PG_HOST = "127.0.0.1"
PG_DB = "rapid_scada"

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
    val_disp = f"({final_val:.1f} cm)" if (cnl_num in (198, 199) and final_val is not None) else (f"({final_val:.1f}°C)" if final_val is not None else "")
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
                if f_temp > 8.0 or f_temp < 2.0:
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

        time.sleep(15.0)


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
            tank_param = params.get("tank", ["1"])[0]
            force_regen = params.get("regenerate", ["0"])[0] == "1"
            suffix = "tank2" if "2" in str(tank_param) else "tank1"
            report_html_path = os.path.join(REPO_DIR, "notes", f"ln2_dipstick_compliance_report_{suffix}.html")
            if not os.path.exists(report_html_path):
                report_html_path = os.path.join(REPO_DIR, "notes", "ln2_dipstick_compliance_report.html")

            if force_regen or not os.path.exists(report_html_path):
                try:
                    subprocess.run(["python3", os.path.join(REPO_DIR, "scripts", "generate_ln2_report.py")], check=True)
                except Exception as e:
                    print(f"Error generating report: {e}")

            if os.path.exists(report_html_path):
                with open(report_html_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
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

        elif parsed.path in ["/report/ln2/chart", "/notes/assets/ln2_sawtooth_chart.png"]:
            params = urllib.parse.parse_qs(parsed.query)
            tank_param = params.get("tank", ["1"])[0]
            suffix = "tank2" if "2" in str(tank_param) else "tank1"
            chart_path = os.path.join(REPO_DIR, "notes", "assets", f"ln2_sawtooth_chart_{suffix}.png")
            if not os.path.exists(chart_path):
                chart_path = os.path.join(REPO_DIR, "notes", "assets", "ln2_sawtooth_chart.png")
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
              <title>IVF Lab Clinical Operations & SCADA Alert Controller</title>
              <style>
                * {{ box-sizing:border-box; }}
                body {{ background:#090d16; color:#f0f4f8; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding:20px 24px 40px; margin:0; }}
                
                /* Top Header & Navigation */
                header {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px; margin-bottom:20px; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:16px; }}
                .brand-title {{ color:#00e5ff; font-size:1.55rem; font-weight:800; margin:0; letter-spacing:-0.3px; }}
                .brand-sub {{ color:#8899a6; font-size:0.85rem; margin-top:3px; }}
                
                .nav-tabs {{ display:inline-flex; background:#101726; padding:4px; border-radius:10px; border:1px solid rgba(255,255,255,0.1); gap:4px; }}
                .nav-tab {{ background:transparent; color:#94a3b8; border:none; padding:10px 20px; border-radius:8px; font-size:14px; font-weight:700; cursor:pointer; transition:all 0.15s; }}
                .nav-tab:hover {{ color:#f8fafc; }}
                .nav-tab.active {{ background:#00e5ff; color:#090d16; box-shadow:0 2px 12px rgba(0,229,255,0.35); }}
                
                .header-meta {{ display:flex; align-items:center; gap:14px; }}
                .badge-live {{ background:rgba(0,230,118,0.12); color:#00e676; border:1px solid rgba(0,230,118,0.4); padding:6px 14px; border-radius:100px; font-size:12px; font-weight:700; display:flex; align-items:center; gap:8px; }}
                .pulse-dot {{ width:8px; height:8px; background:#00e676; border-radius:50%; box-shadow:0 0 8px #00e676; animation:pulse 1.5s infinite; }}
                @keyframes pulse {{ 0% {{ opacity:0.4; }} 50% {{ opacity:1; }} 100% {{ opacity:0.4; }} }}
                .clock-display {{ font-family:monospace; font-size:13px; color:#8899a6; font-weight:600; }}

                /* Daily QA Banner (Top of Main Page) */
                .qa-banner {{ background:linear-gradient(135deg, rgba(16,23,38,0.95), rgba(18,28,45,0.85)); border:1px solid rgba(0,230,118,0.3); border-left:5px solid #00e676; border-radius:12px; padding:16px 20px; margin-bottom:20px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px; box-shadow:0 4px 20px rgba(0,0,0,0.35); }}
                .qa-title {{ font-size:1.05rem; font-weight:700; color:#f0f4f8; margin:0 0 4px; display:flex; align-items:center; gap:10px; }}
                .qa-desc {{ font-size:13px; color:#94a3b8; margin:0; }}
                .btn-test {{ background:#00e676; color:#090d16; font-size:14px; font-weight:800; padding:10px 22px; border-radius:8px; cursor:pointer; border:none; box-shadow:0 4px 14px rgba(0,230,118,0.3); transition:all 0.15s; }}
                .btn-test:hover {{ background:#00c853; transform:translateY(-1px); }}

                /* Telemetry Grid (Main Page) */
                .grid-telemetry {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:16px; margin-bottom:24px; }}
                .card {{ background:rgba(18,25,41,0.85); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:18px; position:relative; overflow:hidden; transition:transform 0.15s; }}
                .card-title {{ color:#8899a6; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px; }}
                .card-val {{ font-size:2.2rem; font-weight:800; font-family:monospace; color:#f0f4f8; line-height:1.1; }}
                .card-unit {{ font-size:1.05rem; color:#8899a6; margin-left:3px; }}
                .card-sub {{ font-size:12px; color:#8899a6; margin-top:8px; display:flex; justify-content:space-between; align-items:center; }}
                
                .status-badge {{ font-size:11px; font-weight:800; padding:3px 8px; border-radius:4px; text-transform:uppercase; letter-spacing:0.4px; }}
                .status-normal {{ background:rgba(0,230,118,0.15); color:#00e676; border:1px solid rgba(0,230,118,0.3); }}
                .status-warn {{ background:rgba(255,171,0,0.15); color:#ffab00; border:1px solid rgba(255,171,0,0.3); }}
                .status-alert {{ background:rgba(255,23,68,0.22); color:#ff1744; border:1px solid rgba(255,23,68,0.4); font-weight:800; animation:pulse-alert 1.5s infinite; }}
                @keyframes pulse-alert {{ 0% {{ opacity:0.8; }} 50% {{ opacity:1; box-shadow:0 0 10px rgba(255,23,68,0.5); }} 100% {{ opacity:0.8; }} }}

                /* Integrated Dipstick Sub-Panel in Cryo Cards */
                .dipstick-subpanel {{ background:rgba(9,13,22,0.75); border:1px solid rgba(0,229,255,0.25); border-radius:10px; padding:12px; margin-top:14px; }}
                .dip-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }}
                .dip-level-row {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px; }}
                .dip-level {{ font-size:1.4rem; font-weight:800; font-family:monospace; color:#00e5ff; }}
                .dip-actions {{ display:flex; gap:8px; margin-top:10px; }}
                .btn-mini {{ background:#00b0ff; color:#090d16; border:none; padding:6px 12px; border-radius:6px; font-size:12px; font-weight:700; cursor:pointer; flex:1; text-align:center; }}
                .btn-mini:hover {{ background:#0091ea; }}
                .btn-mini-subtle {{ background:transparent; color:#00e5ff; border:1px solid rgba(0,229,255,0.3); padding:6px 10px; border-radius:6px; font-size:12px; font-weight:600; cursor:pointer; text-decoration:none; }}
                .btn-mini-subtle:hover {{ background:rgba(0,229,255,0.1); }}

                /* Sub-Page Layout */
                .subpage-header {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px; margin-bottom:20px; }}
                .subpage-title {{ color:#00e5ff; font-size:1.45rem; font-weight:800; margin:0 0 4px; }}
                .subpage-desc {{ color:#8899a6; font-size:0.9rem; margin:0; }}
                .btn-report {{ text-decoration:none; display:inline-flex; align-items:center; gap:6px; background:#00897b; font-weight:700; padding:10px 16px; border-radius:8px; font-size:13px; color:#ffffff; box-shadow:0 4px 14px rgba(0,137,123,0.3); }}
                .btn-report:hover {{ background:#00796b; }}
                
                /* Large Cryo Detail Cards */
                .cryo-detail-grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:18px; margin-bottom:24px; }}
                .cryo-card-lg {{ background:rgba(18,25,41,0.85); border:1px solid rgba(255,255,255,0.08); border-radius:14px; padding:22px; position:relative; }}
                .metrics-row {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; background:rgba(9,13,22,0.6); padding:12px; border-radius:10px; margin:14px 0; border:1px solid rgba(255,255,255,0.05); }}
                .metric-label {{ font-size:11px; color:#8899a6; text-transform:uppercase; font-weight:600; margin-bottom:4px; }}
                .metric-val {{ font-size:1.15rem; font-weight:800; font-family:monospace; color:#f0f4f8; }}

                /* Chart Showcase */
                .chart-container {{ background:rgba(9,13,22,0.9); border:1px solid rgba(255,255,255,0.1); border-radius:12px; padding:16px; margin-top:14px; text-align:center; }}
                .chart-img {{ width:100%; max-height:420px; object-fit:contain; border-radius:8px; }}

                /* Section Cards & Tables */
                .section-card {{ background:rgba(18,25,41,0.85); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:20px; margin-bottom:20px; }}
                table {{ width:100%; border-collapse:collapse; margin-top:12px; }}
                th, td {{ padding:10px 14px; text-align:left; border-bottom:1px solid rgba(255,255,255,0.06); font-size:13.5px; }}
                th {{ color:#8899a6; text-transform:uppercase; font-size:11.5px; letter-spacing:0.5px; }}
                .btn {{ background:#2979ff; color:white; border:none; padding:8px 16px; border-radius:6px; cursor:pointer; font-weight:600; }}
                .btn:hover {{ background:#1e6cd9; }}

                /* LN2 Modal & Glove-Friendly Stepper */
                .modal-overlay {{ position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(4,8,18,0.88); backdrop-filter:blur(6px); display:flex; justify-content:center; align-items:center; z-index:9999; }}
                .modal-box {{ background:#101726; border:1px solid rgba(0,229,255,0.35); border-radius:16px; padding:24px; max-width:540px; width:92%; box-shadow:0 16px 40px rgba(0,0,0,0.7); max-height:90vh; overflow-y:auto; }}
                .form-group {{ margin-bottom:16px; }}
                .form-label {{ display:block; font-size:12px; font-weight:700; color:#8899a6; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px; }}
                .stepper-row {{ display:flex; align-items:center; gap:8px; }}
                .btn-stepper {{ background:#1e293b; color:#f0f4f8; border:1px solid rgba(255,255,255,0.15); border-radius:8px; font-weight:700; font-size:15px; padding:12px 14px; cursor:pointer; min-width:52px; text-align:center; }}
                .btn-stepper:hover {{ background:#334155; }}
                .input-level {{ flex:1; background:#090d16; border:1px solid rgba(0,229,255,0.5); border-radius:8px; color:#00e5ff; font-family:monospace; font-size:1.8rem; font-weight:700; text-align:center; padding:8px 0; }}
                .chips-row {{ display:flex; flex-wrap:wrap; gap:8px; }}
                .chip {{ background:#1e293b; color:#cbd5e1; border:1px solid rgba(255,255,255,0.1); border-radius:8px; padding:10px 16px; font-size:14px; font-weight:600; cursor:pointer; user-select:none; transition:all 0.15s; }}
                .chip:hover {{ background:#283548; }}
                .chip.active {{ background:rgba(0,229,255,0.22); color:#00e5ff; border-color:#00e5ff; font-weight:700; box-shadow:0 0 10px rgba(0,229,255,0.2); }}
                .chip-fill {{ background:#1e293b; color:#cbd5e1; border:1px solid rgba(255,255,255,0.1); border-radius:8px; padding:12px 16px; font-size:14px; font-weight:600; cursor:pointer; flex:1; text-align:center; transition:all 0.15s; }}
                .chip-fill.active {{ background:rgba(0,230,118,0.2); color:#00e676; border-color:#00e676; font-weight:700; box-shadow:0 0 10px rgba(0,230,118,0.2); }}
                .text-input {{ width:100%; box-sizing:border-box; background:#090d16; border:1px solid rgba(255,255,255,0.15); border-radius:8px; color:#f0f4f8; font-size:14px; padding:10px 12px; }}
                .text-input:focus {{ outline:none; border-color:#00e5ff; }}
              </style>
            </head>
            <body>
              <!-- Top Global Header -->
              <header>
                <div>
                  <h1 class="brand-title">IVF Cleanroom Operations & SCADA Alert Controller</h1>
                  <div class="brand-sub">Advanced Fertility of Alaska — Clinical Embryology & Cryopreservation</div>
                </div>

                <!-- Navigation Tabs -->
                <div class="nav-tabs">
                  <button class="nav-tab active" id="tab-live" onclick="switchTab('live')">🌡️ Live Operations</button>
                  <button class="nav-tab" id="tab-cryo" onclick="switchTab('cryo')">🧊 Cryo Tank Audit</button>
                </div>

                <div class="header-meta">
                  <div class="clock-display" id="liveClock">--:--:-- AKDT</div>
                  <div class="badge-live"><div class="pulse-dot"></div> Telemetry Live</div>
                </div>
              </header>

              <!-- ============================================================== -->
              <!-- PAGE 1: REAL-TIME CLINICAL OPERATIONS                          -->
              <!-- ============================================================== -->
              <div id="view-live">
                <!-- 1. Top Section: Daily Alarm Verification (CAP/CLIA) -->
                <div class="qa-banner">
                  <div>
                    <div class="qa-title">
                      <span>Daily Alarm Pathway Verification (CAP / CLIA)</span>
                      <span id="qaBadge" class="status-badge status-normal" style="font-size:11px;">PENDING</span>
                    </div>
                    <p class="qa-desc" id="qaStatusText">
                      Dispatches verified Priority 0 pathway test to on-call embryology team and logs regulatory timestamp in PostgreSQL.
                    </p>
                  </div>
                  <div>
                    <button class="btn-test" onclick="runDailyTest()">🔔 Run Daily Alarm Pathway Test</button>
                  </div>
                </div>
                <div id="testStatus" style="margin:-12px 0 16px; font-size:13px; font-weight:600; padding:0 8px;"></div>

                <!-- 2. Middle Section: Live Real-Time Telemetry Grid -->
                <div class="grid-telemetry">
                  <!-- Cryo Tank 1 (Embryos) -->
                  <div class="card" id="card-cryo1" style="border-top:3px solid #00e5ff;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                      <div>
                        <div class="card-title">Cryo Tank 1 (Embryos)</div>
                        <div class="card-val"><span id="val-cryo1">--</span><span class="card-unit">°C</span></div>
                      </div>
                      <span id="badge-cryo1" class="status-badge status-normal">NORMAL</span>
                    </div>
                    <div class="card-sub">
                      <span>Vapor Limit: &lt; -135.0°C</span>
                      <span style="font-size:11px; color:#8899a6;">Pt100 Analog</span>
                    </div>

                    <!-- Integrated Dipstick Sub-Panel -->
                    <div class="dipstick-subpanel" id="dip-subpanel-1">
                      <div class="dip-header">
                        <span style="font-size:11.5px; font-weight:700; color:#00e5ff; text-transform:uppercase;">Manual Dipstick</span>
                        <span id="badge-ln2-1" class="status-badge status-normal">ON SCHEDULE</span>
                      </div>
                      <div class="dip-level-row">
                        <div><span class="dip-level" id="val-ln2-level-1">--</span><span style="color:#8899a6; font-size:12px;"> cm</span></div>
                        <span id="sub-ln2-check-1" style="font-size:12px; color:#8899a6;">--</span>
                      </div>
                      <div id="ln2-next-due-1" style="font-size:11px; color:#8899a6; margin-top:2px;">Next: Mon/Wed/Fri by 5:00 PM</div>
                      <div class="dip-actions">
                        <button class="btn-mini" onclick="openLn2ModalFor('Cryo Tank 1')">🧊 Log Check</button>
                        <button class="btn-mini-subtle" onclick="switchTab('cryo')">Audit Trail →</button>
                      </div>
                    </div>
                  </div>

                  <!-- Cryo Tank 2 (Sperm) -->
                  <div class="card" id="card-cryo2" style="border-top:3px solid #00b0ff;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                      <div>
                        <div class="card-title">Cryo Tank 2 (Sperm)</div>
                        <div class="card-val"><span id="val-cryo2">--</span><span class="card-unit">°C</span></div>
                      </div>
                      <span id="badge-cryo2" class="status-badge status-normal">NORMAL</span>
                    </div>
                    <div class="card-sub">
                      <span>Vapor Limit: &lt; -135.0°C</span>
                      <span style="font-size:11px; color:#8899a6;">Pt100 Analog</span>
                    </div>

                    <!-- Integrated Dipstick Sub-Panel -->
                    <div class="dipstick-subpanel" id="dip-subpanel-2">
                      <div class="dip-header">
                        <span style="font-size:11.5px; font-weight:700; color:#00b0ff; text-transform:uppercase;">Manual Dipstick</span>
                        <span id="badge-ln2-2" class="status-badge status-normal">ON SCHEDULE</span>
                      </div>
                      <div class="dip-level-row">
                        <div><span class="dip-level" id="val-ln2-level-2">--</span><span style="color:#8899a6; font-size:12px;"> cm</span></div>
                        <span id="sub-ln2-check-2" style="font-size:12px; color:#8899a6;">--</span>
                      </div>
                      <div id="ln2-next-due-2" style="font-size:11px; color:#8899a6; margin-top:2px;">Next: Mon/Wed/Fri by 5:00 PM</div>
                      <div class="dip-actions">
                        <button class="btn-mini" onclick="openLn2ModalFor('Cryo Tank 2')">🧊 Log Check</button>
                        <button class="btn-mini-subtle" onclick="switchTab('cryo')">Audit Trail →</button>
                      </div>
                    </div>
                  </div>

                  <!-- Combined Medical Cold Storage (Fridge & Freezer) -->
                  <div class="card" id="card-cold-storage" style="border-top:3px solid #00e676;">
                    <div class="card-title">Medical Cold Storage</div>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:8px;">
                      <!-- Fridge Section -->
                      <div style="background:rgba(9,13,22,0.65); padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.06);">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                          <span style="font-size:11px; font-weight:700; color:#8899a6; text-transform:uppercase;">Med Fridge</span>
                          <span id="badge-fridge" class="status-badge status-normal">NORMAL</span>
                        </div>
                        <div style="font-size:1.75rem; font-weight:800; font-family:monospace; color:#f0f4f8; line-height:1.1;">
                          <span id="val-fridge">--</span><span class="card-unit">°C</span>
                        </div>
                        <div style="font-size:11px; color:#8899a6; margin-top:5px;">Target: 2.0°C – 8.0°C</div>
                      </div>
                      <!-- Freezer Section -->
                      <div style="background:rgba(9,13,22,0.65); padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.06);">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                          <span style="font-size:11px; font-weight:700; color:#8899a6; text-transform:uppercase;">Med Freezer</span>
                          <span id="badge-freezer" class="status-badge status-normal">NORMAL</span>
                        </div>
                        <div style="font-size:1.75rem; font-weight:800; font-family:monospace; color:#f0f4f8; line-height:1.1;">
                          <span id="val-freezer">--</span><span class="card-unit">°C</span>
                        </div>
                        <div style="font-size:11px; color:#8899a6; margin-top:5px;">Limit: &lt; -15.0°C</div>
                      </div>
                    </div>
                  </div>

                  <!-- Cleanroom Ambient -->
                  <div class="card" id="card-ambient">
                    <div class="card-title">Cleanroom Ambient</div>
                    <div class="card-val"><span id="val-ambient">--</span><span class="card-unit">°C</span></div>
                    <div class="card-sub">
                      <span>Comfort Target: ~25.0°C</span>
                      <span id="badge-ambient" class="status-badge status-normal">COMFORT</span>
                    </div>
                  </div>

                  <!-- Combined Cleanroom Doors Card -->
                  <div class="card" id="card-doors" style="border-top:3px solid #2979ff;">
                    <div class="card-title">Cleanroom Doors & Access</div>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:8px;">
                      <!-- Main Door Section -->
                      <div style="background:rgba(9,13,22,0.65); padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.06);">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                          <span style="font-size:11px; font-weight:700; color:#8899a6; text-transform:uppercase;">Main Door</span>
                          <span id="badge-door1" class="status-badge status-normal">SECURE</span>
                        </div>
                        <div style="font-size:1.55rem; font-weight:800; font-family:monospace; color:#f0f4f8; margin-top:2px;" id="val-door1">
                          CLOSED
                        </div>
                        <div style="font-size:11px; color:#8899a6; margin-top:5px;">Limit: &lt; 3m open</div>
                      </div>
                      <!-- Cryo Door Section -->
                      <div style="background:rgba(9,13,22,0.65); padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.06);">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                          <span style="font-size:11px; font-weight:700; color:#8899a6; text-transform:uppercase;">Cryo Lab Door</span>
                          <span id="badge-door2" class="status-badge status-normal">SECURE</span>
                        </div>
                        <div style="font-size:1.55rem; font-weight:800; font-family:monospace; color:#f0f4f8; margin-top:2px;" id="val-door2">
                          CLOSED
                        </div>
                        <div style="font-size:11px; color:#8899a6; margin-top:5px;">Limit: &lt; 3m open</div>
                      </div>
                    </div>
                  </div>

                  <!-- Chamber Incubators -->
                  <div class="card" id="card-incubators">
                    <div class="card-title">Chamber Incubators</div>
                    <div class="card-val" id="val-incubators" style="font-size:1.6rem; margin-top:6px;">NORMAL</div>
                    <div class="card-sub">
                      <span>Incubator 01 & 02</span>
                      <span id="badge-incubators" class="status-badge status-normal">ALL CLEAR</span>
                    </div>
                  </div>
                </div>

                <!-- 3. Bottom Section: Active Alarms & Clinical Audit Trail -->
                <div class="section-card">
                  <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:8px;">
                    <div>
                      <h3 style="margin:0; font-size:1.15rem; color:#f0f4f8;">Active Alarms & Clinical Audit Trail</h3>
                      <p style="color:#8899a6; font-size:13px; margin:3px 0 0;">Reverse chronological history. Tap Acknowledge to silence repeating sirens.</p>
                    </div>
                  </div>
                  <div id="alarmsTable">Loading alarms...</div>
                </div>
              </div>

              <!-- ============================================================== -->
              <!-- PAGE 2: CRYO TANK AUDIT & DIPSTICK SUITE                       -->
              <!-- ============================================================== -->
              <div id="view-cryo" style="display:none;">
                <!-- Sub-Page Header -->
                <div class="subpage-header">
                  <div>
                    <h2 class="subpage-title">Liquid Nitrogen (LN2) Cryopreservation Suite</h2>
                    <p class="subpage-desc">Dual Tank Manual Dipstick Tracking, Boil-off Dynamics & Regulatory Audit Trail (CAP / CLIA / JCAHO)</p>
                  </div>
                  <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                    <a href="/report/ln2?tank=1" target="_blank" class="btn-report">📊 Print Tank 1 Report</a>
                    <a href="/report/ln2?tank=2" target="_blank" class="btn-report">📊 Print Tank 2 Report</a>
                    <button class="btn" style="background:#00e5ff; color:#090d16; font-size:14px; font-weight:800; padding:10px 18px; border-radius:8px; box-shadow:0 4px 14px rgba(0,229,255,0.3);" onclick="openLn2Modal()">🧊 Log Dipstick Check</button>
                  </div>
                </div>

                <!-- Detailed Cryo Level Overview Cards -->
                <div class="cryo-detail-grid">
                  <!-- Tank 1 Detail -->
                  <div class="cryo-card-lg" style="border-top:4px solid #00e5ff;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                      <div>
                        <div style="font-size:13px; font-weight:700; color:#00e5ff; text-transform:uppercase;">Cryo Tank 1 (Embryos)</div>
                        <div style="font-size:2.4rem; font-weight:800; font-family:monospace; color:#f0f4f8; margin-top:4px;">
                          <span id="detail-ln2-level-1">--</span><span style="font-size:1.2rem; color:#8899a6;"> cm</span>
                        </div>
                      </div>
                      <span id="detail-badge-ln2-1" class="status-badge status-normal">ON SCHEDULE</span>
                    </div>

                    <div class="metrics-row">
                      <div>
                        <div class="metric-label">Vapor Temp</div>
                        <div class="metric-val" style="color:#00e5ff;"><span id="detail-cryo1-temp">--</span>°C</div>
                      </div>
                      <div>
                        <div class="metric-label">Boil-off Rate</div>
                        <div class="metric-val">~1.0 <span style="font-size:11px; color:#8899a6;">cm/d</span></div>
                      </div>
                      <div>
                        <div class="metric-label">Last Refill</div>
                        <div class="metric-val" style="font-size:0.95rem;" id="detail-refill-1">Oct 21</div>
                      </div>
                    </div>

                    <div style="font-size:12.5px; color:#8899a6; line-height:1.6;">
                      <div><b>Last Check:</b> <span id="detail-last-check-1">--</span></div>
                      <div><b>Schedule:</b> <span id="detail-next-check-1">Mon / Wed / Fri by 5:00 PM</span></div>
                    </div>
                    <button class="btn" style="width:100%; background:#00b0ff; font-weight:800; margin-top:14px; padding:12px; border-radius:8px;" onclick="openLn2ModalFor('Cryo Tank 1')">🧊 Log Tank 1 Check</button>
                  </div>

                  <!-- Tank 2 Detail -->
                  <div class="cryo-card-lg" style="border-top:4px solid #00b0ff;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                      <div>
                        <div style="font-size:13px; font-weight:700; color:#00b0ff; text-transform:uppercase;">Cryo Tank 2 (Sperm)</div>
                        <div style="font-size:2.4rem; font-weight:800; font-family:monospace; color:#f0f4f8; margin-top:4px;">
                          <span id="detail-ln2-level-2">--</span><span style="font-size:1.2rem; color:#8899a6;"> cm</span>
                        </div>
                      </div>
                      <span id="detail-badge-ln2-2" class="status-badge status-normal">ON SCHEDULE</span>
                    </div>

                    <div class="metrics-row">
                      <div>
                        <div class="metric-label">Vapor Temp</div>
                        <div class="metric-val" style="color:#00b0ff;"><span id="detail-cryo2-temp">--</span>°C</div>
                      </div>
                      <div>
                        <div class="metric-label">Boil-off Rate</div>
                        <div class="metric-val">~1.0 <span style="font-size:11px; color:#8899a6;">cm/d</span></div>
                      </div>
                      <div>
                        <div class="metric-label">Last Refill</div>
                        <div class="metric-val" style="font-size:0.95rem;" id="detail-refill-2">Oct 23</div>
                      </div>
                    </div>

                    <div style="font-size:12.5px; color:#8899a6; line-height:1.6;">
                      <div><b>Last Check:</b> <span id="detail-last-check-2">--</span></div>
                      <div><b>Schedule:</b> <span id="detail-next-check-2">Mon / Wed / Fri by 5:00 PM</span></div>
                    </div>
                    <button class="btn" style="width:100%; background:#00b0ff; font-weight:800; margin-top:14px; padding:12px; border-radius:8px;" onclick="openLn2ModalFor('Cryo Tank 2')">🧊 Log Tank 2 Check</button>
                  </div>
                </div>

                <!-- Sawtooth Curves Showcase -->
                <div class="section-card">
                  <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:12px;">
                    <div>
                      <h3 style="margin:0; font-size:1.15rem; color:#f0f4f8;">60-Day Liquid Nitrogen Level & Refill Sawtooth Curves</h3>
                      <p style="color:#8899a6; font-size:13px; margin:3px 0 0;">Visual confirmation of continuous boil-off rate and refill volume adherence.</p>
                    </div>
                    <div class="chips-row">
                      <div class="chip active" id="chip-chart-1" onclick="switchSawtooth(1)">Tank 1 (Embryos) Curve</div>
                      <div class="chip" id="chip-chart-2" onclick="switchSawtooth(2)">Tank 2 (Sperm) Curve</div>
                    </div>
                  </div>
                  <div class="chart-container">
                    <img id="sawtoothImg" src="/report/ln2/chart?tank=1" alt="LN2 Sawtooth Chart" class="chart-img">
                  </div>
                </div>

                <!-- Full Liquid Nitrogen Audit Trail Table -->
                <div class="section-card">
                  <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:10px;">
                    <div>
                      <h3 style="margin:0; font-size:1.15rem; color:#f0f4f8;">Liquid Nitrogen Manual Dipstick Audit Trail</h3>
                      <p style="color:#8899a6; font-size:13px; margin:3px 0 0;">Complete regulatory history for level verification, manual refills, and seal inspections.</p>
                    </div>
                  </div>
                  <div id="ln2HistoryTable">Loading inspection logs...</div>
                </div>
              </div>

              <!-- ============================================================== -->
              <!-- GLOVE-FRIENDLY LN2 INSPECTION MODAL                            -->
              <!-- ============================================================== -->
              <div id="ln2Modal" class="modal-overlay" style="display:none;">
                <div class="modal-box">
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:18px;">
                    <div>
                      <h2 style="margin:0; font-size:1.3rem; color:#00e5ff;">🧊 Record LN2 Dipstick Check</h2>
                      <div style="color:#8899a6; font-size:12px; margin-top:3px;">Mon / Wed / Fri Cleanroom Schedule (Due by 5:00 PM)</div>
                    </div>
                    <button type="button" class="btn" style="background:transparent; border:1px solid rgba(255,255,255,0.2); font-size:16px; padding:6px 12px;" onclick="closeLn2Modal()">✕</button>
                  </div>

                  <div class="form-group">
                    <label class="form-label">Tank Identifier</label>
                    <div class="chips-row">
                      <div class="chip active" id="chip-tank-1" onclick="selectTank('Cryo Tank 1')">Cryo Tank 1 (Embryos)</div>
                      <div class="chip" id="chip-tank-2" onclick="selectTank('Cryo Tank 2')">Cryo Tank 2 (Sperm)</div>
                    </div>
                  </div>

                  <div class="form-group">
                    <label class="form-label">Dipstick Level (cm)</label>
                    <div class="stepper-row">
                      <button type="button" class="btn-stepper" onclick="adjustLn2(-1.0)">- 1.0</button>
                      <button type="button" class="btn-stepper" onclick="adjustLn2(-0.5)">- 0.5</button>
                      <input type="number" step="0.1" id="ln2LevelInput" class="input-level" value="30.0">
                      <button type="button" class="btn-stepper" onclick="adjustLn2(0.5)">+ 0.5</button>
                      <button type="button" class="btn-stepper" onclick="adjustLn2(1.0)">+ 1.0</button>
                    </div>
                  </div>

                  <div class="form-group">
                    <label class="form-label">Nitrogen Added / Topped Off?</label>
                    <div class="chips-row">
                      <div class="chip-fill active" id="fill-no" onclick="selectFill(false)">🔘 No (Level Check Only)</div>
                      <div class="chip-fill" id="fill-yes" onclick="selectFill(true)">🔵 Yes (Tank Filled to Full)</div>
                    </div>
                  </div>

                  <div class="form-group">
                    <label class="form-label">Staff Initials</label>
                    <div class="chips-row" style="margin-bottom:8px;">
                      <div class="chip" onclick="selectInit('BO')">BO</div>
                      <div class="chip" onclick="selectInit('SJ')">SJ</div>
                      <div class="chip" onclick="selectInit('AK')">AK</div>
                      <div class="chip" onclick="selectInit('TL')">TL</div>
                    </div>
                    <input type="text" id="ln2InitialsInput" class="text-input" placeholder="Type initials (e.g. BO)" maxlength="8">
                  </div>

                  <div class="form-group">
                    <label class="form-label">Visual Inspection / Neck Seal</label>
                    <div class="chips-row">
                      <div class="chip active" id="seal-good" onclick="selectSeal('Good')">Normal / Good Seal</div>
                      <div class="chip" id="seal-frost" onclick="selectSeal('Neck Frost')">Neck Frost</div>
                      <div class="chip" id="seal-concern" onclick="selectSeal('Vacuum Concern')">Vacuum Concern</div>
                    </div>
                  </div>

                  <div class="form-group">
                    <label class="form-label">Notes (Optional)</label>
                    <input type="text" id="ln2NotesInput" class="text-input" placeholder="Optional notes (e.g. routine top-off, inspected o-ring)">
                  </div>

                  <div id="modalSubmitMsg" style="font-size:13px; font-weight:600; margin-bottom:12px;"></div>

                  <div style="display:flex; justify-content:flex-end; gap:12px; margin-top:18px;">
                    <button type="button" class="btn" style="background:#334155;" onclick="closeLn2Modal()">Cancel</button>
                    <button type="button" class="btn" style="background:#00e5ff; color:#090d16; font-size:15px; font-weight:700; padding:10px 24px;" onclick="submitLn2Log()">✅ Submit Inspection</button>
                  </div>
                </div>
              </div>

              <!-- ============================================================== -->
              <!-- SCRIPTS                                                        -->
              <!-- ============================================================== -->
              <script>
                // Navigation / Tabs Controller
                function switchTab(tab, updateUrl = true) {{
                  const isLive = (tab === 'live');
                  document.getElementById('view-live').style.display = isLive ? 'block' : 'none';
                  document.getElementById('view-cryo').style.display = isLive ? 'none' : 'block';
                  document.getElementById('tab-live').className = isLive ? 'nav-tab active' : 'nav-tab';
                  document.getElementById('tab-cryo').className = isLive ? 'nav-tab' : 'nav-tab active';
                  
                  if (updateUrl) {{
                    const targetPath = isLive ? '/' : '/cryo';
                    if (window.location.pathname !== targetPath) {{
                      window.history.pushState({{ tab }}, '', targetPath);
                    }}
                  }}
                }}

                window.addEventListener('popstate', (e) => {{
                  const tab = (e.state && e.state.tab) || (window.location.pathname.startsWith('/cryo') ? 'cryo' : 'live');
                  switchTab(tab, false);
                }});

                function switchSawtooth(tankNum) {{
                  document.getElementById('sawtoothImg').src = '/report/ln2/chart?tank=' + tankNum + '&t=' + Date.now();
                  document.getElementById('chip-chart-1').className = (tankNum === 1) ? 'chip active' : 'chip';
                  document.getElementById('chip-chart-2').className = (tankNum === 2) ? 'chip active' : 'chip';
                }}

                // Telemetry & Alarm Updates
                function updateTelemetry() {{
                  fetch('/api/status')
                    .then(r => r.json())
                    .then(data => {{
                      const r = data.readings || {{}};
                      
                      // Clock
                      if (data.server_time) {{
                        const timeOnly = data.server_time.split(' ')[1] || '';
                        document.getElementById('liveClock').innerText = timeOnly + ' AKDT';
                      }}

                      // Daily QA Verification Status
                      const qa = data.last_qa;
                      const qaBadge = document.getElementById('qaBadge');
                      const qaText = document.getElementById('qaStatusText');
                      if (qa && qa.triggered_at) {{
                        const todayDateStr = (data.server_time || '').split(' ')[0];
                        const qaDateStr = qa.triggered_at.split(' ')[0];
                        const qaTimeStr = (qa.triggered_at.split(' ')[1] || '').split('.')[0];
                        if (todayDateStr && qaDateStr === todayDateStr) {{
                          qaBadge.innerText = 'VERIFIED TODAY';
                          qaBadge.className = 'status-badge status-normal';
                          qaText.innerText = `✅ Verified Today at ${{qaTimeStr}} by ${{qa.by || 'Lab Kiosk'}} (Priority 0 pathway operational).`;
                        }} else {{
                          qaBadge.innerText = 'PENDING TODAY';
                          qaBadge.className = 'status-badge status-warn';
                          qaText.innerText = `⚠️ Daily pathway test pending for today. Last run on ${{qaDateStr}} at ${{qaTimeStr}}.`;
                        }}
                      }}

                      // Ambient (101)
                      if (r[101] !== undefined) {{
                        document.getElementById('val-ambient').innerText = r[101].toFixed(1);
                      }}

                      // Fridge (Ch 102 Temp, Ch 111 PLC Alarm)
                      if (r[102] !== undefined) {{
                        const f = r[102];
                        document.getElementById('val-fridge').innerText = f.toFixed(1);
                        const b = document.getElementById('badge-fridge');
                        const isAlarm = (r[111] !== undefined) ? (r[111] > 0) : (f > 8.0 || f < 2.0);
                        if (isAlarm) {{
                          b.innerText = 'EXCURSION';
                          b.className = 'status-badge status-alert';
                        }} else if (f > 8.0 || f < 2.0) {{
                          b.innerText = 'DELAY (2M)';
                          b.className = 'status-badge status-warn';
                        }} else {{
                          b.innerText = 'NORMAL';
                          b.className = 'status-badge status-normal';
                        }}
                      }}

                      // Freezer (Ch 103 Temp, Ch 112 PLC Alarm)
                      if (r[103] !== undefined) {{
                        const fz = r[103];
                        document.getElementById('val-freezer').innerText = fz.toFixed(1);
                        const b = document.getElementById('badge-freezer');
                        const isAlarm = (r[112] !== undefined) ? (r[112] > 0) : (fz > -15.0);
                        if (isAlarm) {{
                          b.innerText = 'EXCURSION';
                          b.className = 'status-badge status-alert';
                        }} else if (fz > -15.0) {{
                          b.innerText = 'DELAY (3M)';
                          b.className = 'status-badge status-warn';
                        }} else {{
                          b.innerText = 'NORMAL';
                          b.className = 'status-badge status-normal';
                        }}
                      }}

                      // Cryo Tank 1 (Ch 125 Temp, Ch 113 PLC Alarm)
                      if (r[125] !== undefined) {{
                        const cr1 = r[125];
                        document.getElementById('val-cryo1').innerText = cr1.toFixed(1);
                        const detailC1 = document.getElementById('detail-cryo1-temp');
                        if (detailC1) detailC1.innerText = cr1.toFixed(1);

                        const b1 = document.getElementById('badge-cryo1');
                        const isAlarm1 = (r[113] !== undefined) ? (r[113] > 0) : (cr1 > -135.0);
                        if (isAlarm1) {{
                          b1.innerText = 'CRITICAL';
                          b1.className = 'status-badge status-alert';
                        }} else if (cr1 > -135.0) {{
                          b1.innerText = 'DELAY (30S)';
                          b1.className = 'status-badge status-warn';
                        }} else {{
                          b1.innerText = 'NORMAL';
                          b1.className = 'status-badge status-normal';
                        }}
                      }}

                      // Cryo Tank 2 (Ch 104 Temp, Ch 114 PLC Alarm)
                      if (r[104] !== undefined) {{
                        const cr2 = r[104];
                        document.getElementById('val-cryo2').innerText = cr2.toFixed(1);
                        const detailC2 = document.getElementById('detail-cryo2-temp');
                        if (detailC2) detailC2.innerText = cr2.toFixed(1);

                        const b2 = document.getElementById('badge-cryo2');
                        const isAlarm2 = (r[114] !== undefined) ? (r[114] > 0) : (cr2 > -135.0);
                        if (isAlarm2) {{
                          b2.innerText = 'CRITICAL';
                          b2.className = 'status-badge status-alert';
                        }} else if (cr2 > -135.0) {{
                          b2.innerText = 'DELAY (30S)';
                          b2.className = 'status-badge status-warn';
                        }} else {{
                          b2.innerText = 'NORMAL';
                          b2.className = 'status-badge status-normal';
                        }}
                      }}

                      // Main Cleanroom Door (Ch 121 PLC Alarm: bDoor01_Alarm)
                      if (r[121] !== undefined) {{
                        const d1Alarm = r[121] > 0;
                        document.getElementById('val-door1').innerText = d1Alarm ? 'AJAR > 3M' : 'CLOSED';
                        document.getElementById('val-door1').style.color = d1Alarm ? '#ff1744' : '#f0f4f8';
                        const b1 = document.getElementById('badge-door1');
                        b1.innerText = d1Alarm ? 'ALARM' : 'SECURE';
                        b1.className = d1Alarm ? 'status-badge status-alert' : 'status-badge status-normal';
                      }}

                      // Cryo Lab Door (Ch 122 PLC Alarm: bDoor02_Alarm)
                      if (r[122] !== undefined) {{
                        const d2Alarm = r[122] > 0;
                        document.getElementById('val-door2').innerText = d2Alarm ? 'AJAR > 3M' : 'CLOSED';
                        document.getElementById('val-door2').style.color = d2Alarm ? '#ff1744' : '#f0f4f8';
                        const b2 = document.getElementById('badge-door2');
                        b2.innerText = d2Alarm ? 'ALARM' : 'SECURE';
                        b2.className = d2Alarm ? 'status-badge status-alert' : 'status-badge status-normal';
                      }}

                      // Incubators (123 & 124)
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
                  st.style.color = '#00e5ff';
                  st.innerText = '⏳ Dispatching test alert to Pushover...';
                  fetch('/api/test', {{ method: 'POST' }})
                    .then(r => r.json())
                    .then(d => {{
                      st.style.color = '#00e676';
                      st.innerText = '✅ Daily Alarm Test dispatched to team at ' + d.timestamp + ' (Pushover Priority 0)';
                      updateTelemetry();
                      loadAlarms();
                      setTimeout(() => {{ st.innerText = ''; }}, 6000);
                    }})
                    .catch(e => {{
                      st.style.color = '#ff1744';
                      st.innerText = '❌ Failed to send test alert';
                    }});
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
                          if (r.priority === 1) {{
                            statusHtml = '<span style="color:#ffab00; font-weight:700;">⚠️ ACTIVE (WARNING)</span>';
                            actHtml = `<button class="btn" style="background:#ffab00; color:#0f172a; font-weight:700;" onclick="ackAlarm(${{r.id}})">✋ Acknowledge</button>`;
                          }} else {{
                            statusHtml = '<span style="color:#ff1744; font-weight:700;">🔴 ACTIVE (SIREN)</span>';
                            actHtml = `<button class="btn" onclick="ackAlarm(${{r.id}})">✋ Acknowledge</button>`;
                          }}
                        }} else if (r.is_acknowledged && !r.is_resolved) {{
                          const tok = r.acknowledged_by_token ? ` title="Immutable Token: ${{r.acknowledged_by_token}}"` : '';
                          statusHtml = `<span style="color:#ffab00; font-weight:600;"${{tok}}>🟡 Attending (${{r.acknowledged_by || 'Staff'}})</span>`;
                        }} else {{
                          statusHtml = '<span style="color:#00e676;">🟢 Resolved</span>';
                        }}
                        const valDisp = r.excursion_val !== null ? ([198, 199].includes(r.cnl_num) ? r.excursion_val + 'h overdue' : r.excursion_val + '°C') : '-';
                        const timeDisp = r.triggered_at ? r.triggered_at.split('.')[0] : '-';
                        h += `<tr><td>${{timeDisp}}</td><td><b>${{r.equipment_name}}</b></td><td>${{r.alarm_type}}</td><td>${{valDisp}}</td><td>${{statusHtml}}</td><td>${{actHtml}}</td></tr>`;
                      }});
                      h += '</tbody></table>';
                      document.getElementById('alarmsTable').innerHTML = h;
                    }});
                }}

                // LN2 Modal & Inspection Handlers
                let currentTank = 'Cryo Tank 1';
                let currentFill = false;
                let currentSeal = 'Good';

                function openLn2Modal() {{
                  document.getElementById('ln2Modal').style.display = 'flex';
                  document.getElementById('modalSubmitMsg').innerText = '';
                }}

                function openLn2ModalFor(tank) {{
                  selectTank(tank);
                  openLn2Modal();
                }}

                function closeLn2Modal() {{
                  document.getElementById('ln2Modal').style.display = 'none';
                }}

                function selectTank(tank) {{
                  currentTank = tank;
                  document.getElementById('chip-tank-1').className = (tank === 'Cryo Tank 1') ? 'chip active' : 'chip';
                  document.getElementById('chip-tank-2').className = (tank === 'Cryo Tank 2') ? 'chip active' : 'chip';
                }}

                function adjustLn2(delta) {{
                  const inp = document.getElementById('ln2LevelInput');
                  let val = parseFloat(inp.value) || 30.0;
                  val = Math.max(0, Math.round((val + delta) * 10) / 10);
                  inp.value = val.toFixed(1);
                }}

                function selectFill(isFilled) {{
                  currentFill = isFilled;
                  document.getElementById('fill-no').className = isFilled ? 'chip-fill' : 'chip-fill active';
                  document.getElementById('fill-yes').className = isFilled ? 'chip-fill active' : 'chip-fill';
                }}

                function selectInit(init) {{
                  document.getElementById('ln2InitialsInput').value = init;
                }}

                function selectSeal(seal) {{
                  currentSeal = seal;
                  document.getElementById('seal-good').className = (seal === 'Good') ? 'chip active' : 'chip';
                  document.getElementById('seal-frost').className = (seal === 'Neck Frost') ? 'chip active' : 'chip';
                  document.getElementById('seal-concern').className = (seal === 'Vacuum Concern') ? 'chip active' : 'chip';
                }}

                function submitLn2Log() {{
                  const lvlStr = document.getElementById('ln2LevelInput').value;
                  const initials = document.getElementById('ln2InitialsInput').value.trim();
                  const notes = document.getElementById('ln2NotesInput').value.trim();
                  const msgEl = document.getElementById('modalSubmitMsg');

                  if (!initials) {{
                    msgEl.style.color = '#ff1744';
                    msgEl.innerText = '⚠️ Please enter staff initials.';
                    return;
                  }}

                  const payload = {{
                    tank_id: currentTank,
                    level_cm: parseFloat(lvlStr),
                    was_filled: currentFill,
                    frost_condition: currentSeal,
                    initials: initials,
                    notes: notes
                  }};

                  msgEl.style.color = '#00e5ff';
                  msgEl.innerText = '⏳ Submitting inspection log...';

                  fetch('/api/ln2_log', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                  }})
                    .then(r => r.json())
                    .then(d => {{
                      if (d.success) {{
                        msgEl.style.color = '#00e676';
                        msgEl.innerText = '✅ ' + d.message;
                        updateLn2Status();
                        loadAlarms();
                        setTimeout(() => {{
                          closeLn2Modal();
                          document.getElementById('ln2NotesInput').value = '';
                        }}, 1200);
                      }} else {{
                        msgEl.style.color = '#ff1744';
                        msgEl.innerText = '❌ ' + (d.error || 'Failed to submit log');
                      }}
                    }})
                    .catch(e => {{
                      msgEl.style.color = '#ff1744';
                      msgEl.innerText = '❌ Error submitting: ' + e;
                    }});
                }}

                function updateLn2Status() {{
                  fetch('/api/ln2_status')
                    .then(r => r.json())
                    .then(data => {{
                      const tanks = data.tanks || {{}};
                      
                      // 1. Update Cryo Tank 1
                      const t1 = tanks['Cryo Tank 1'];
                      if (t1) {{
                        const lvl1 = t1.level_cm.toFixed(1);
                        const hrs1 = `${{t1.hours_since.toFixed(1)}}h ago (${{t1.initials}})`;
                        const due1 = t1.detail || `Next: ${{t1.next_check}}`;
                        const badgeTxt1 = t1.badge || 'ON SCHEDULE';

                        // Main Card Elements
                        const el1 = document.getElementById('val-ln2-level-1');
                        if (el1) el1.innerText = lvl1;
                        const b1 = document.getElementById('badge-ln2-1');
                        if (b1) b1.innerText = badgeTxt1;
                        const sub1 = document.getElementById('sub-ln2-check-1');
                        if (sub1) sub1.innerText = hrs1;
                        const nextDue1 = document.getElementById('ln2-next-due-1');
                        if (nextDue1) nextDue1.innerText = due1;

                        // Subpage Detail Elements
                        const dEl1 = document.getElementById('detail-ln2-level-1');
                        if (dEl1) dEl1.innerText = lvl1;
                        const dB1 = document.getElementById('detail-badge-ln2-1');
                        if (dB1) dB1.innerText = badgeTxt1;
                        const dCheck1 = document.getElementById('detail-last-check-1');
                        if (dCheck1) dCheck1.innerText = `${{t1.level_cm.toFixed(1)}} cm (${{hrs1}})`;
                        const dNext1 = document.getElementById('detail-next-check-1');
                        if (dNext1) dNext1.innerText = t1.next_check;

                        const badgeClass1 = (t1.status === 'OVERDUE') ? 'status-badge status-alert' :
                                           ((t1.status === 'DUE') ? 'status-badge status-warn' : 'status-badge status-normal');
                        if (b1) b1.className = badgeClass1;
                        if (dB1) dB1.className = badgeClass1;
                      }}

                      // 2. Update Cryo Tank 2
                      const t2 = tanks['Cryo Tank 2'];
                      if (t2) {{
                        const lvl2 = t2.level_cm.toFixed(1);
                        const hrs2 = `${{t2.hours_since.toFixed(1)}}h ago (${{t2.initials}})`;
                        const due2 = t2.detail || `Next: ${{t2.next_check}}`;
                        const badgeTxt2 = t2.badge || 'ON SCHEDULE';

                        // Main Card Elements
                        const el2 = document.getElementById('val-ln2-level-2');
                        if (el2) el2.innerText = lvl2;
                        const b2 = document.getElementById('badge-ln2-2');
                        if (b2) b2.innerText = badgeTxt2;
                        const sub2 = document.getElementById('sub-ln2-check-2');
                        if (sub2) sub2.innerText = hrs2;
                        const nextDue2 = document.getElementById('ln2-next-due-2');
                        if (nextDue2) nextDue2.innerText = due2;

                        // Subpage Detail Elements
                        const dEl2 = document.getElementById('detail-ln2-level-2');
                        if (dEl2) dEl2.innerText = lvl2;
                        const dB2 = document.getElementById('detail-badge-ln2-2');
                        if (dB2) dB2.innerText = badgeTxt2;
                        const dCheck2 = document.getElementById('detail-last-check-2');
                        if (dCheck2) dCheck2.innerText = `${{t2.level_cm.toFixed(1)}} cm (${{hrs2}})`;
                        const dNext2 = document.getElementById('detail-next-check-2');
                        if (dNext2) dNext2.innerText = t2.next_check;

                        const badgeClass2 = (t2.status === 'OVERDUE') ? 'status-badge status-alert' :
                                           ((t2.status === 'DUE') ? 'status-badge status-warn' : 'status-badge status-normal');
                        if (b2) b2.className = badgeClass2;
                        if (dB2) dB2.className = badgeClass2;
                      }}

                      // 3. Render History Table
                      const hist = data.history || [];
                      const tableContainer = document.getElementById('ln2HistoryTable');
                      if (tableContainer) {{
                        if (hist.length === 0) {{
                          tableContainer.innerHTML = '<p style="color:#8899a6; padding:8px 0;">No inspection logs recorded.</p>';
                          return;
                        }}
                        let th = '<table><thead><tr><th>Logged Time</th><th>Tank</th><th>Level (cm)</th><th>Filled?</th><th>Neck Seal</th><th>Initials</th><th>Notes</th></tr></thead><tbody>';
                        hist.forEach(row => {{
                          const timeStr = row.logged_at ? row.logged_at.split('.')[0] : '-';
                          const fillBadge = row.was_filled ? '<span style="color:#00e676; font-weight:700;">🔵 Yes (Filled)</span>' : '<span style="color:#8899a6;">Check Only</span>';
                          const sealColor = (row.frost_condition === 'Good') ? '#00e676' : '#ffab00';
                          th += `<tr><td>${{timeStr}}</td><td><b>${{row.tank_id}}</b></td><td style="color:#00e5ff; font-family:monospace; font-weight:700; font-size:15px;">${{row.level_cm.toFixed(1)}} cm</td><td>${{fillBadge}}</td><td><span style="color:${{sealColor}};">${{row.frost_condition}}</span></td><td><b>${{row.initials}}</b></td><td style="color:#8899a6;">${{row.notes || '-'}}</td></tr>`;
                        }});
                        th += '</tbody></table>';
                        tableContainer.innerHTML = th;
                      }}
                    }})
                    .catch(e => console.error('LN2 fetch error:', e));
                }}

                // Initialization
                const initialTab = (window.location.pathname.startsWith('/cryo') || window.location.hash === '#cryo') ? 'cryo' : 'live';
                switchTab(initialTab, false);

                setInterval(updateTelemetry, 1000);
                setInterval(loadAlarms, 2000);
                setInterval(updateLn2Status, 3000);
                updateTelemetry();
                loadAlarms();
                updateLn2Status();
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
    print(f"Ready. Listening for Kiosk / Web API calls on http://0.0.0.0:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down gracefully.")
        server.server_close()


if __name__ == "__main__":
    main()

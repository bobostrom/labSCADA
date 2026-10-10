#!/usr/bin/env python3
"""
IVF Lab SCADA Watchdog & Pushover Alert Service
Monitors Incubator Alarm (Channel 122) and Rapid SCADA polling health.
Sends Priority 2 Emergency Alerts (bypassing silent mode with sirens) to Pushover for Teams.
Automatically cancels repeating emergency alarms when the contact returns to Normal.
"""

import time
import os
import re
import urllib.request
import urllib.parse
import json
import logging
from datetime import datetime

# ================= Configuration =================
PUSHOVER_TOKEN = "a2wmo7ofxhhpo2vc2ykdkhtnte8nb5"
PUSHOVER_USER_OR_GROUP = "gepqspoh98t69c7o223hwbg8ponwyq"
DEVICE_LOG_PATH = "/var/log/scada/ScadaComm/Log/device001.txt"
CHECK_INTERVAL_SECONDS = 1.0
STALE_HEARTBEAT_THRESHOLD_SECONDS = 60.0

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

def send_pushover(title, message, priority=0, sound="pushover", retry=60, expire=3600):
    """
    Send notification to Pushover API.
    Returns (success_bool, receipt_id_or_none).
    """
    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_TOKEN,
        "user": PUSHOVER_USER_OR_GROUP,
        "title": title,
        "message": message,
        "priority": priority,
        "sound": sound,
    }
    if priority == 2:
        data["retry"] = retry
        data["expire"] = expire

    encoded_data = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded_data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            receipt = res_json.get("receipt")
            logging.info(f"Pushover sent: {title} (Receipt: {receipt})")
            return True, receipt
    except Exception as e:
        logging.error(f"Failed to send Pushover notification: {e}")
        return False, None

def cancel_pushover_receipt(receipt):
    """Cancels a repeating Priority 2 emergency alert in Pushover."""
    if not receipt:
        return
    url = f"https://api.pushover.net/1/receipts/cancel/{receipt}.json"
    data = urllib.parse.urlencode({"token": PUSHOVER_TOKEN}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            logging.info(f"Pushover emergency repeat canceled for receipt {receipt}: {res_body}")
    except Exception as e:
        logging.error(f"Failed to cancel Pushover receipt {receipt}: {e}")

def parse_device_status():
    """
    Parses device001.txt to extract:
    - Last modified time
    - Communicator Status (e.g. Normal)
    - IncubatorAlarm_01 state (e.g. 'On' or 'Off')
    """
    if not os.path.exists(DEVICE_LOG_PATH):
        return None, "File missing", None

    try:
        mtime = os.path.getmtime(DEVICE_LOG_PATH)
        with open(DEVICE_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Check overall status
        status_match = re.search(r"Status\s*:\s*(\w+)", content)
        status = status_match.group(1) if status_match else "Unknown"

        # Check IncubatorAlarm_01 line
        alarm_match = re.search(r"IncubatorAlarm_01\s*\|\s*IncubatorAlarm_01\s*\|\s*(\w+)", content)
        alarm_state = alarm_match.group(1) if alarm_match else None

        return mtime, status, alarm_state
    except Exception as e:
        logging.error(f"Error reading {DEVICE_LOG_PATH}: {e}")
        return None, "Read error", None

def main():
    logging.info("Starting IVF Lab Watchdog Service...")
    
    last_alarm_state = None
    active_emergency_receipt = None
    scada_stale_alerted = False

    while True:
        try:
            mtime, comm_status, alarm_state = parse_device_status()
            now = time.time()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 1. Check SCADA Heartbeat / Stale Log
            if mtime is None or (now - mtime) > STALE_HEARTBEAT_THRESHOLD_SECONDS:
                if not scada_stale_alerted:
                    age = int(now - mtime) if mtime else 999
                    logging.warning(f"SCADA log stale! Age: {age}s")
                    send_pushover(
                        title="⚠️ WATCHDOG: IVF SCADA Offline",
                        message=f"Rapid SCADA has not updated device logs for {age} seconds at {now_str}. Monitoring may be offline!",
                        priority=1,
                        sound="falling"
                    )
                    scada_stale_alerted = True
            else:
                if scada_stale_alerted:
                    logging.info("SCADA log recovered.")
                    send_pushover(
                        title="✅ WATCHDOG: IVF SCADA Recovered",
                        message=f"Rapid SCADA polling resumed at {now_str}.",
                        priority=0,
                        sound="pushover"
                    )
                    scada_stale_alerted = False

            # 2. Check Incubator Alarm State Transition
            if alarm_state is not None:
                if last_alarm_state is None:
                    # Initial state recorded
                    last_alarm_state = alarm_state
                    logging.info(f"Initial Incubator Alarm State: {alarm_state}")
                elif alarm_state != last_alarm_state:
                    logging.warning(f"Incubator Alarm State changed: {last_alarm_state} -> {alarm_state}")
                    if alarm_state.lower() == "on":
                        # TRIPPED! Send Emergency siren alert
                        success, receipt = send_pushover(
                            title="🚨 CRITICAL ALARM: Incubator 1",
                            message=f"Incubator 1 alarm contact TRIPPED at {now_str}! Check incubator chamber temperature, CO2, and power immediately.",
                            priority=2, # Emergency: overrides silent mode, repeats every 60s
                            sound="siren",
                            retry=60,
                            expire=7200
                        )
                        active_emergency_receipt = receipt
                    elif alarm_state.lower() == "off":
                        # Normal again! Automatically cancel repeating emergency alarm
                        if active_emergency_receipt:
                            logging.info(f"Canceling active emergency repeat: {active_emergency_receipt}")
                            cancel_pushover_receipt(active_emergency_receipt)
                            active_emergency_receipt = None

                        # Send resolution alert
                        send_pushover(
                            title="✅ RESOLVED: Incubator 1 Normal",
                            message=f"Incubator 1 alarm contact returned to Normal state at {now_str}.",
                            priority=0,
                            sound="magic"
                        )
                    last_alarm_state = alarm_state

        except Exception as e:
            logging.error(f"Watchdog main loop exception: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()

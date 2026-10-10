#!/usr/bin/env python3
"""
IVF Lab SCADA Clinical Web Dashboard & Alert Controller
Serves a responsive clinical dashboard on port 8080 with live status,
temperature gauges, door sensors, and interactive Test / Ack buttons.
"""

import http.server
import socketserver
import json
import urllib.parse
import urllib.request
import re
import os
import time
from datetime import datetime

PORT = 8080
DEVICE_LOG_PATH = "/var/log/scada/ScadaComm/Log/device001.txt"
PUSHOVER_TOKEN = "a2wmo7ofxhhpo2vc2ykdkhtnte8nb5"
PUSHOVER_GROUP = "gepqspoh98t69c7o223hwbg8ponwyq"
PUSHOVER_PING_URL = "https://api.pushover.net/1/monitors/mm5z3n2shg9hjn2785oyu649ri92cxh/ping.json"

# State tracking for acknowledgment & active alerts
state_lock = False
active_emergency_receipt = None
last_ack_time = None
last_ack_by = None

def get_live_data():
    """Parses device001.txt for real-time status."""
    data = {
        "status": "Offline",
        "last_updated": "Never",
        "age_seconds": 999,
        "temperatures": {},
        "incubators": {
            "incubator_1": "Off",
            "incubator_2": "Off"
        },
        "doors": {
            "door_1": "Off",
            "door_2": "Off"
        },
        "sensors": {}
    }

    if not os.path.exists(DEVICE_LOG_PATH):
        return data

    try:
        mtime = os.path.getmtime(DEVICE_LOG_PATH)
        age = int(time.time() - mtime)
        data["age_seconds"] = age
        data["last_updated"] = datetime.fromtimestamp(mtime).strftime("%H:%M:%S")

        with open(DEVICE_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line in lines:
            if "Status" in line and ":" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    data["status"] = parts[1].strip()

            # Parse table rows: | 1 | Temperature_01 | Temperature_01 | 254 | 101 |
            if "|" in line:
                cols = [c.strip() for c in line.split("|") if c.strip()]
                if len(cols) >= 4:
                    tag = cols[1]
                    val_str = cols[3]

                    if tag.startswith("Temperature_"):
                        try:
                            # Divide by 10 for true float reading
                            raw_val = float(val_str)
                            data["temperatures"][tag] = round(raw_val / 10.0, 1)
                        except:
                            data["temperatures"][tag] = val_str

                    elif tag == "IncubatorAlarm_01":
                        data["incubators"]["incubator_1"] = val_str
                    elif tag == "IncubatorAlarm_02":
                        data["incubators"]["incubator_2"] = val_str
                    elif tag == "DoorOpen_01":
                        data["doors"]["door_1"] = val_str
                    elif tag == "DoorOpen_02":
                        data["doors"]["door_2"] = val_str
                    elif tag.startswith("SensorStatus_"):
                        data["sensors"][tag] = val_str

    except Exception as e:
        print(f"Error parsing device log: {e}")

    return data

def send_pushover_alert(title, message, priority=0, sound="pushover", retry=60, expire=3600):
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
        post_data["retry"] = retry
        post_data["expire"] = expire

    encoded = urllib.parse.urlencode(post_data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            res_body = res.read().decode("utf-8")
            res_json = json.loads(res_body)
            return True, res_json.get("receipt")
    except Exception as e:
        print(f"Pushover error: {e}")
        return False, None

def cancel_pushover(receipt):
    if not receipt:
        return False
    url = f"https://api.pushover.net/1/receipts/cancel/{receipt}.json"
    encoded = urllib.parse.urlencode({"token": PUSHOVER_TOKEN}).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as res:
            return True
    except Exception as e:
        print(f"Cancel error: {e}")
        return False

# Embed rich, responsive HTML dashboard
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>IVF Lab Monitor</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(18, 25, 41, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --accent-cyan: #00e5ff;
      --accent-blue: #2979ff;
      --green: #00e676;
      --green-glow: rgba(0, 230, 118, 0.25);
      --red: #ff1744;
      --red-glow: rgba(255, 23, 68, 0.4);
      --amber: #ffab00;
      --text: #f0f4f8;
      --text-muted: #8899a6;
      --font-main: 'Inter', -apple-system, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      background-image: 
        radial-gradient(at 0% 0%, rgba(41, 121, 255, 0.12) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(0, 229, 255, 0.08) 0px, transparent 50%);
      color: var(--text);
      font-family: var(--font-main);
      min-height: 100vh;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }

    /* Header Bar */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--card-border);
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-icon {
      width: 44px;
      height: 44px;
      background: linear-gradient(135deg, var(--accent-blue), var(--accent-cyan));
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 22px;
      box-shadow: 0 4px 16px rgba(0, 229, 255, 0.3);
    }
    h1 {
      font-size: 1.4rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .subtitle {
      font-size: 0.85rem;
      color: var(--text-muted);
    }
    .system-status {
      display: flex;
      align-items: center;
      gap: 16px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      padding: 8px 16px;
      border-radius: 100px;
      backdrop-filter: blur(10px);
    }
    .heartbeat-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 10px var(--green);
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
    }

    /* Action Buttons Row */
    .actions-bar {
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
    }
    .btn {
      flex: 1;
      min-width: 220px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      padding: 14px 24px;
      font-family: var(--font-main);
      font-size: 0.95rem;
      font-weight: 600;
      border-radius: 12px;
      border: 1px solid transparent;
      cursor: pointer;
      transition: all 0.2s ease;
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    .btn:active { transform: scale(0.98); }
    .btn-test {
      background: rgba(41, 121, 255, 0.15);
      border-color: rgba(41, 121, 255, 0.4);
      color: #82b1ff;
    }
    .btn-test:hover {
      background: rgba(41, 121, 255, 0.25);
      box-shadow: 0 0 20px rgba(41, 121, 255, 0.3);
    }
    .btn-ack {
      background: rgba(255, 171, 0, 0.15);
      border-color: rgba(255, 171, 0, 0.4);
      color: #ffd740;
    }
    .btn-ack:hover {
      background: rgba(255, 171, 0, 0.25);
      box-shadow: 0 0 20px rgba(255, 171, 0, 0.3);
    }

    /* Grid Layout */
    .dashboard-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 20px;
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 20px;
      backdrop-filter: blur(12px);
      display: flex;
      flex-direction: column;
      gap: 16px;
      transition: border 0.3s ease;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .card-title {
      font-size: 0.85rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    /* Device Card States */
    .device-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(255, 255, 255, 0.03);
      padding: 14px 16px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.04);
    }
    .device-name {
      font-weight: 600;
      font-size: 1rem;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px;
      border-radius: 100px;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.04em;
    }
    .badge-normal {
      background: rgba(0, 230, 118, 0.15);
      border: 1px solid rgba(0, 230, 118, 0.4);
      color: var(--green);
    }
    .badge-alarm {
      background: var(--red);
      color: #fff;
      box-shadow: 0 0 20px var(--red-glow);
      animation: alertBlink 1s infinite alternate;
    }
    @keyframes alertBlink {
      from { box-shadow: 0 0 10px var(--red-glow); }
      to { box-shadow: 0 0 25px rgba(255, 23, 68, 0.8); }
    }
    .badge-closed {
      background: rgba(0, 230, 118, 0.12);
      border: 1px solid rgba(0, 230, 118, 0.3);
      color: var(--green);
    }
    .badge-open {
      background: rgba(255, 171, 0, 0.2);
      border: 1px solid rgba(255, 171, 0, 0.5);
      color: var(--amber);
    }

    /* Temperature Readout Cards */
    .temp-readout {
      display: flex;
      align-items: baseline;
      gap: 6px;
      font-family: var(--font-mono);
      font-size: 2.2rem;
      font-weight: 700;
      color: #fff;
    }
    .temp-unit {
      font-size: 1.1rem;
      color: var(--accent-cyan);
      font-family: var(--font-main);
    }
    .temp-bar-bg {
      height: 6px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 3px;
      overflow: hidden;
      margin-top: 6px;
    }
    .temp-bar-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--accent-blue), var(--accent-cyan));
      border-radius: 3px;
      transition: width 0.5s ease;
    }

    /* Toast Notifications */
    #toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #1e293b;
      border: 1px solid var(--accent-cyan);
      color: #fff;
      padding: 14px 20px;
      border-radius: 12px;
      font-weight: 600;
      box-shadow: 0 8px 30px rgba(0,0,0,0.5);
      opacity: 0;
      transform: translateY(20px);
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      pointer-events: none;
      z-index: 1000;
    }
    #toast.show {
      opacity: 1;
      transform: translateY(0);
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="brand-icon">🔬</div>
      <div>
        <h1>IVF Lab Monitor</h1>
        <div class="subtitle">Schweitzer SEL RTAC • Rapid SCADA v6 • Pushover Protected</div>
      </div>
    </div>
    <div class="system-status">
      <div class="heartbeat-dot" id="scadaDot"></div>
      <span id="scadaText" style="font-weight: 600; font-size: 0.85rem;">SCADA Online</span>
      <span id="lastUpdated" style="font-size: 0.8rem; color: var(--text-muted); font-family: var(--font-mono);">--:--:--</span>
    </div>
  </header>

  <!-- Interactive Control Buttons -->
  <div class="actions-bar">
    <button class="btn btn-test" id="btnTest" onclick="sendSystemTest()">
      <span>🔔</span> Send System Alarm Test
    </button>
    <button class="btn btn-ack" id="btnAck" onclick="sendAcknowledge()">
      <span>🔕</span> Acknowledge / Silence Active Siren
    </button>
  </div>

  <div class="dashboard-grid">

    <!-- Incubators Card -->
    <div class="card" id="cardIncubators">
      <div class="card-header">
        <div class="card-title">🧫 Incubator Chambers</div>
        <span style="font-size: 0.75rem; color: var(--text-muted);">Channels 123 - 124</span>
      </div>

      <div class="device-row">
        <div>
          <div class="device-name">Incubator 1 (Chamber A)</div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">Modbus Discrete Input 12</div>
        </div>
        <div class="badge badge-normal" id="badgeInc1">● NORMAL</div>
      </div>

      <div class="device-row">
        <div>
          <div class="device-name">Incubator 2 (Chamber B)</div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">Modbus Discrete Input 13</div>
        </div>
        <div class="badge badge-normal" id="badgeInc2">● NORMAL</div>
      </div>
    </div>

    <!-- Cleanroom Doors Card -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">🚪 Lab Entry</div>
        <span style="font-size: 0.75rem; color: var(--text-muted);">Channels 121 - 122</span>
      </div>

      <div class="device-row">
        <div>
          <div class="device-name">Main Lab Door</div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">Modbus Discrete Input 10</div>
        </div>
        <div class="badge badge-closed" id="badgeDoor1">CLOSED</div>
      </div>

      <div class="device-row">
        <div>
          <div class="device-name">Procedure Room Door</div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">Modbus Discrete Input 11</div>
        </div>
        <div class="badge badge-closed" id="badgeDoor2">CLOSED</div>
      </div>
    </div>

    <!-- Temperature Zone 1 Card -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">🌡️ Cryo / Zone 1 Temp</div>
        <span style="font-size: 0.75rem; color: var(--text-muted);">Channel 101</span>
      </div>
      <div>
        <div class="temp-readout">
          <span id="temp1">--.-</span>
          <span class="temp-unit">°C</span>
        </div>
        <div class="temp-bar-bg">
          <div class="temp-bar-fill" id="tempBar1" style="width: 50%;"></div>
        </div>
      </div>
      <div style="font-size: 0.8rem; color: var(--text-muted);">Holding Register 0 (RTAC scaled /10)</div>
    </div>

    <!-- Temperature Zone 2 Card -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">🌡️ Lab Ambient / Zone 2 Temp</div>
        <span style="font-size: 0.75rem; color: var(--text-muted);">Channel 102</span>
      </div>
      <div>
        <div class="temp-readout">
          <span id="temp2">--.-</span>
          <span class="temp-unit">°C</span>
        </div>
        <div class="temp-bar-bg">
          <div class="temp-bar-fill" id="tempBar2" style="width: 50%;"></div>
        </div>
      </div>
      <div style="font-size: 0.8rem; color: var(--text-muted);">Holding Register 1 (RTAC scaled /10)</div>
    </div>

  </div>

  <div id="toast">Message sent</div>

  <script>
    function showToast(text) {
      const t = document.getElementById('toast');
      t.innerText = text;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 3500);
    }

    async function sendSystemTest() {
      const btn = document.getElementById('btnTest');
      btn.disabled = true;
      btn.innerText = "⏳ Sending Test...";
      try {
        const res = await fetch('/api/test', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          showToast("🔔 System Test Notification sent to Pushover Teams!");
        } else {
          showToast("⚠️ Failed to send test notification");
        }
      } catch (e) {
        showToast("⚠️ Network error sending test");
      }
      setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = "<span>🔔</span> Send System Alarm Test";
      }, 3000);
    }

    async function sendAcknowledge() {
      const btn = document.getElementById('btnAck');
      btn.disabled = true;
      btn.innerText = "⏳ Acknowledging...";
      try {
        const res = await fetch('/api/ack', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          showToast("🔕 Siren Silenced & Alarm Acknowledged on Pushover!");
        } else {
          showToast("ℹ️ " + (data.message || "No active emergency sirens to cancel"));
        }
      } catch (e) {
        showToast("⚠️ Error acknowledging alarm");
      }
      setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = "<span>🔕</span> Acknowledge / Silence Active Siren";
      }, 3000);
    }

    async function pollStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();

        // Update Header
        document.getElementById('lastUpdated').innerText = data.last_updated;
        if (data.age_seconds > 20) {
          document.getElementById('scadaDot').style.background = '#ff1744';
          document.getElementById('scadaText').innerText = 'SCADA Stale (' + data.age_seconds + 's)';
        } else {
          document.getElementById('scadaDot').style.background = '#00e676';
          document.getElementById('scadaText').innerText = 'SCADA Live (' + data.status + ')';
        }

        // Update Incubators
        const inc1Badge = document.getElementById('badgeInc1');
        if (data.incubators.incubator_1 === 'On') {
          inc1Badge.className = 'badge badge-alarm';
          inc1Badge.innerText = '🚨 ALARM TRIPPED';
        } else {
          inc1Badge.className = 'badge badge-normal';
          inc1Badge.innerText = '● NORMAL';
        }

        const inc2Badge = document.getElementById('badgeInc2');
        if (data.incubators.incubator_2 === 'On') {
          inc2Badge.className = 'badge badge-alarm';
          inc2Badge.innerText = '🚨 ALARM TRIPPED';
        } else {
          inc2Badge.className = 'badge badge-normal';
          inc2Badge.innerText = '● NORMAL';
        }

        // Update Doors
        const door1Badge = document.getElementById('badgeDoor1');
        if (data.doors.door_1 === 'On') {
          door1Badge.className = 'badge badge-open';
          door1Badge.innerText = '⚠️ DOOR OPEN';
        } else {
          door1Badge.className = 'badge badge-closed';
          door1Badge.innerText = 'CLOSED';
        }

        const door2Badge = document.getElementById('badgeDoor2');
        if (data.doors.door_2 === 'On') {
          door2Badge.className = 'badge badge-open';
          door2Badge.innerText = '⚠️ DOOR OPEN';
        } else {
          door2Badge.className = 'badge badge-closed';
          door2Badge.innerText = 'CLOSED';
        }

        // Update Temperatures
        if (data.temperatures.Temperature_01 !== undefined) {
          document.getElementById('temp1').innerText = data.temperatures.Temperature_01;
          const pct = Math.min(Math.max((data.temperatures.Temperature_01 / 50) * 100, 5), 100);
          document.getElementById('tempBar1').style.width = pct + '%';
        }
        if (data.temperatures.Temperature_02 !== undefined) {
          document.getElementById('temp2').innerText = data.temperatures.Temperature_02;
          const pct2 = Math.min(Math.max((data.temperatures.Temperature_02 / 50) * 100, 5), 100);
          document.getElementById('tempBar2').style.width = pct2 + '%';
        }

      } catch (e) {
        document.getElementById('scadaDot').style.background = '#ff1744';
        document.getElementById('scadaText').innerText = 'Comms Lost';
      }
    }

    // Poll every 1.5 seconds
    setInterval(pollStatus, 1500);
    pollStatus();
  </script>
</body>
</html>
"""

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/dashboard"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            data = get_live_data()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global active_emergency_receipt, last_ack_time, last_ack_by
        now_str = datetime.now().strftime("%H:%M:%S")

        if self.path == "/api/test":
            success, _ = send_pushover_alert(
                title="🔔 IVF LAB QA: Alarm System Test",
                message=f"Alarm pathway test initiated by Web Dashboard at {now_str}. All systems operational.",
                priority=0,
                sound="magic"
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))

        elif self.path == "/api/ack":
            # 1. Send Acknowledgment Notification to the team
            send_pushover_alert(
                title="🔕 ALARM ACKNOWLEDGED",
                message=f"Active alarm was physically acknowledged via Web Dashboard at {now_str}. Siren silenced.",
                priority=0,
                sound="pushover"
            )

            # 2. If an emergency receipt is active, cancel its repeats
            if active_emergency_receipt:
                cancel_pushover(active_emergency_receipt)
                active_emergency_receipt = None

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "message": "Alarm silenced and acknowledged"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), DashboardHandler) as httpd:
        print(f"IVF Clinical Dashboard running on http://0.0.0.0:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    run_server()

#!/usr/bin/env python3
"""Standalone Pushover Inactivity Monitor watchdog for LabSCADA hosts.

Verifies that core Rapid SCADA services, the IVF alert engine HTTP/DB path,
and ScadaComm polling logs are healthy before sending the per-site
PUSHOVER_PING_URL heartbeat from /etc/labscada/site.env.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_SITE_ENV = "/etc/labscada/site.env"
REQUIRED_SERVICES = (
    "scadaserver6.service",
    "scadacomm6.service",
    "ivf-alert-engine.service",
)
DEFAULT_STATUS_URL = "http://127.0.0.1:8080/api/status"
DEFAULT_COMM_LOG = "/var/log/scada/ScadaComm/Log/device001.txt"
DEFAULT_MAX_LOG_AGE_SEC = 180
DEFAULT_INTERVAL_SEC = 60

_stop_requested = False


def _handle_signal(signum, _frame):
    global _stop_requested
    _stop_requested = True
    print(f"[watchdog] Received signal {signum}, stopping...", flush=True)


def load_env_file(path):
    """Loads KEY=VALUE pairs from path without overriding existing env vars."""
    if not path or not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)


def check_systemd_services(services):
    """Returns (ok, reason) verifying each required systemd service is active."""
    for svc in services:
        try:
            proc = subprocess.run(
                ["systemctl", "is-active", "--quiet", svc],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if proc.returncode != 0:
                return False, f"service {svc} is not active"
        except Exception as exc:
            return False, f"failed checking {svc}: {exc}"
    return True, "services active"


def check_alert_engine_api(status_url, timeout=5):
    """Verifies ivf-alert-engine responds cleanly with live telemetry JSON."""
    req = urllib.request.Request(
        status_url,
        headers={"User-Agent": "labscada-watchdog/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return False, f"{status_url} returned HTTP {resp.status}"
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return False, f"{status_url} request failed: {exc}"

    if not isinstance(payload, dict) or "server_time" not in payload or "readings" not in payload:
        return False, f"{status_url} returned unexpected JSON shape"
    return True, "alert engine API healthy"


def check_comm_log_freshness(log_path, max_age_sec):
    """Verifies ScadaComm device log was updated within max_age_sec."""
    if max_age_sec <= 0:
        return True, "log freshness check disabled"
    if not os.path.exists(log_path):
        return False, f"ScadaComm log missing: {log_path}"
    age = time.time() - os.path.getmtime(log_path)
    if age > max_age_sec:
        return False, f"ScadaComm log stale ({int(age)}s > {max_age_sec}s)"
    return True, f"ScadaComm log fresh ({int(age)}s)"


def check_host_health():
    """Runs all SCADA host health checks. Returns (ok, summary)."""
    ok, reason = check_systemd_services(REQUIRED_SERVICES)
    if not ok:
        return False, reason

    status_url = os.environ.get("WATCHDOG_STATUS_URL", DEFAULT_STATUS_URL)
    ok, reason = check_alert_engine_api(status_url)
    if not ok:
        return False, reason

    comm_log = os.environ.get("WATCHDOG_COMM_LOG", DEFAULT_COMM_LOG)
    max_age = int(os.environ.get("WATCHDOG_MAX_LOG_AGE_SECONDS", DEFAULT_MAX_LOG_AGE_SEC))
    ok, reason = check_comm_log_freshness(comm_log, max_age)
    if not ok:
        return False, reason

    return True, "all checks passed"


def ping_pushover(ping_url, timeout=10):
    """Sends a heartbeat ping to Pushover's monitor endpoint. Returns (ok, detail)."""
    req = urllib.request.Request(
        ping_url,
        headers={"User-Agent": "labscada-watchdog/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace").strip()
            if resp.status != 200:
                return False, f"HTTP {resp.status}: {body}"
            try:
                data = json.loads(body)
                if data.get("status") != 1:
                    return False, f"unexpected Pushover response: {body}"
            except ValueError:
                pass
            return True, body
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace').strip()}"
    except Exception as exc:
        return False, str(exc)


def run_cycle():
    """Executes one watchdog verification and ping cycle. Returns True if OK."""
    ping_url = os.environ.get("PUSHOVER_PING_URL", "").strip()
    if not ping_url:
        print("[watchdog] PUSHOVER_PING_URL is empty; skipping ping.", flush=True)
        return True
    if not ping_url.startswith("https://"):
        print(f"[watchdog] SKIPPED: invalid PUSHOVER_PING_URL ({ping_url})", file=sys.stderr, flush=True)
        return False

    ok, summary = check_host_health()
    if not ok:
        print(f"[watchdog] UNHEALTHY - ping withheld: {summary}", file=sys.stderr, flush=True)
        return False

    ping_ok, detail = ping_pushover(ping_url)
    if not ping_ok:
        print(f"[watchdog] PING FAILED: {detail}", file=sys.stderr, flush=True)
        return False

    site = os.environ.get("CLINIC_SLUG", "unknown")
    print(f"[watchdog] OK ({site}): {summary}; pinged Pushover ({detail})", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description="LabSCADA Pushover Health Watchdog")
    parser.add_argument("--once", action="store_true", help="Run one check/ping cycle and exit")
    parser.add_argument("--interval", type=int, default=0, help="Override ping interval in seconds")
    parser.add_argument("--env-file", default=DEFAULT_SITE_ENV, help="Path to site.env")
    args = parser.parse_args()

    load_env_file(args.env_file)

    if args.once:
        sys.exit(0 if run_cycle() else 1)

    interval = args.interval or int(os.environ.get("WATCHDOG_INTERVAL_SECONDS", DEFAULT_INTERVAL_SEC))
    interval = max(15, interval)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    print(
        f"[watchdog] Started (site={os.environ.get('CLINIC_SLUG', 'unknown')}, interval={interval}s)",
        flush=True,
    )

    while not _stop_requested:
        try:
            run_cycle()
        except Exception as exc:
            print(f"[watchdog] Unexpected error: {exc}", file=sys.stderr, flush=True)

        deadline = time.monotonic() + interval
        while not _stop_requested and time.monotonic() < deadline:
            time.sleep(min(1.0, max(0.1, deadline - time.monotonic())))


if __name__ == "__main__":
    main()

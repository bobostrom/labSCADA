#!/usr/bin/env python3
"""
==============================================================================
Clinical SCADA Tool: sync_plc_config.py
==============================================================================
Synchronizes clinical trip limits, thresholds, and operational setpoints from
equipment.json (Single Source of Truth) directly into the CODESYS PLC runtime
over OPC UA (IEC 61131-3 RAM variables).

Eliminates dual-entry and allows adjusting setpoints without opening CODESYS IDE
or restarting the PLC.

Usage:
    python3 sync_plc_config.py --read                  # Read current PLC setpoints
    python3 sync_plc_config.py --dry-run               # Preview changes from equipment.json
    python3 sync_plc_config.py                         # Synchronize and verify all limits
    python3 sync_plc_config.py --config /path/to.json  # Custom manifest path
==============================================================================
"""

import os
import sys
import json
import argparse
import asyncio
from typing import Dict, Any, List, Tuple

# Configuration & Security defaults
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PLC_URL = os.environ.get("PLC_OPC_URL", "opc.tcp://192.168.10.136:4840")
DEFAULT_USER = os.environ.get("PLC_OPC_USER", "scada")
DEFAULT_PASS = os.environ.get("PLC_OPC_PASS", "labMon@2026")
CERT_FILE = os.environ.get("OPC_CLIENT_CERT", "/etc/labscada/certs/client_cert.pem")
KEY_FILE = os.environ.get("OPC_CLIENT_KEY", "/etc/labscada/certs/client_key.pem")
APP_URI = os.environ.get("OPC_APP_URI", "urn:demo-scada:RapidScada:DrvOpcUa")

DEVICE_PREFIXES = [
    "WAGO 750-8212 PFC200 G2 2ETH RS.Application",
    "CODESYS Control for Raspberry Pi 64 SL.Application",
]


def find_equipment_config(custom_path: str = None) -> Tuple[str, Dict[str, Any]]:
    """Locates and loads equipment.json from candidates."""
    candidates = []
    if custom_path:
        candidates.append(custom_path)
    candidates.extend([
        "/etc/labscada/equipment.json",
        os.path.join(REPO_DIR, "equipment.json"),
        os.path.join(REPO_DIR, "sites", "demo", "equipment.json"),
        os.path.join(REPO_DIR, "sites", "afoa", "equipment.json"),
    ])

    for path in candidates:
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return path, data
            except Exception as e:
                print(f"[!] Warning: Failed parsing {path}: {e}")

    raise FileNotFoundError("Could not find equipment.json in any expected location.")


def extract_plc_setpoints(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extracts target limits from equipment.json and maps them to PLC OPC UA variable suffixes."""
    setpoints = []

    # 1. Medical Refrigerators
    for f in cfg.get("fridges", []):
        fb = f.get("plc_fb", "fbColdStorage")
        # In hierarchical composition, fbColdStorage contains fbFridge
        var_base = f"PLC_PRG.{fb}.fbFridge" if fb == "fbColdStorage" else f"PLC_PRG.{fb}"
        if "low_limit" in f and f["low_limit"] is not None:
            setpoints.append({
                "name": f"{f.get('name', 'Fridge')} Low Trip",
                "suffix": f"{var_base}.rLowTrip",
                "target": float(f["low_limit"]),
                "unit": "°C",
            })
        if "high_limit" in f and f["high_limit"] is not None:
            setpoints.append({
                "name": f"{f.get('name', 'Fridge')} High Trip",
                "suffix": f"{var_base}.rHighTrip",
                "target": float(f["high_limit"]),
                "unit": "°C",
            })

    # 2. Medical Freezers
    for fz in cfg.get("freezers", []):
        fb = fz.get("plc_fb", "fbColdStorage")
        var_base = f"PLC_PRG.{fb}.fbFreezer" if fb == "fbColdStorage" else f"PLC_PRG.{fb}"
        if "high_limit" in fz and fz["high_limit"] is not None:
            setpoints.append({
                "name": f"{fz.get('name', 'Freezer')} High Trip",
                "suffix": f"{var_base}.rHighTrip",
                "target": float(fz["high_limit"]),
                "unit": "°C",
            })

    # 3. Cryogenic LN2 Dewars
    for d in cfg.get("dewars", []):
        fb = d.get("plc_fb")
        if fb and "high_limit" in d and d["high_limit"] is not None:
            setpoints.append({
                "name": f"{d.get('name', 'Dewar')} High Trip",
                "suffix": f"PLC_PRG.{fb}.rHighTrip",
                "target": float(d["high_limit"]),
                "unit": "°C",
            })

    # 4. Cleanroom Ambient Room Comfort
    for a in cfg.get("ambient", []):
        if "low_limit" in a and a["low_limit"] is not None:
            setpoints.append({
                "name": "Cleanroom Ambient Low Trip",
                "suffix": "PLC_PRG.fbColdStorage.rAmbientLowTrip",
                "target": float(a["low_limit"]),
                "unit": "°C",
            })
        if "high_limit" in a and a["high_limit"] is not None:
            setpoints.append({
                "name": "Cleanroom Ambient High Trip",
                "suffix": "PLC_PRG.fbColdStorage.rAmbientHighTrip",
                "target": float(a["high_limit"]),
                "unit": "°C",
            })

    # 5. Incubator Cabinet (Thermostatic fan setpoint)
    for c in cfg.get("cabinets", []):
        fb = c.get("plc_fb", "fbCabinet01")
        if "fan_setpoint" in c and c["fan_setpoint"] is not None:
            setpoints.append({
                "name": f"{c.get('name', 'Cabinet')} Fan Setpoint",
                "suffix": f"PLC_PRG.{fb}.rFanOnSetpoint",
                "target": float(c["fan_setpoint"]),
                "unit": "°C",
            })

    return setpoints


async def run_opc_sync(setpoints: List[Dict[str, Any]], plc_url: str, user: str, password: str, mode: str, quiet: bool = False) -> Dict[str, Any]:
    """Connects to CODESYS OPC UA server, reads current values, and writes targets if mode == 'write'."""
    try:
        from asyncua import Client, ua
        from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256
    except ImportError:
        err = "ERROR: 'asyncua' library is required. Install via: pip install asyncua"
        if not quiet:
            print(f"[!] {err}")
        return {"success": False, "error": err, "updated_count": 0, "match_count": 0, "results": []}

    if not quiet:
        print(f"\n[*] Connecting to CODESYS OPC UA Server at {plc_url}...")
    client = Client(plc_url, timeout=5)

    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        client.application_uri = APP_URI
        await client.set_security(
            SecurityPolicyBasic256Sha256,
            certificate=CERT_FILE,
            private_key=KEY_FILE,
            mode=3  # SignAndEncrypt
        )
        if not quiet:
            print(f"[*] Security configured: Basic256Sha256 (SignAndEncrypt) with {CERT_FILE}")
    
    if user:
        client.set_user(user)
        if password:
            client.set_password(password)

    results = []
    async with client:
        if not quiet:
            print("[+] Connected to OPC UA Server successfully.\n")

        # Discover active prefix
        active_prefix = None
        for prefix in DEVICE_PREFIXES:
            test_node_id = f"ns=4;s=|var|{prefix}.PLC_PRG.rLabAmbientTemp"
            try:
                test_node = client.get_node(test_node_id)
                await test_node.read_value()
                active_prefix = prefix
                break
            except Exception:
                continue

        if not active_prefix:
            active_prefix = DEVICE_PREFIXES[1]  # Default to Raspberry Pi

        if not quiet:
            print(f"[*] Detected Device Prefix: {active_prefix}\n")
            print(f"{'PARAMETER':<32} | {'PLC CURRENT':<12} | {'TARGET (JSON)':<14} | {'STATUS'}")
            print("-" * 75)

        updated_count = 0
        match_count = 0

        for sp in setpoints:
            node_id = f"ns=4;s=|var|{active_prefix}.{sp['suffix']}"
            name = sp["name"]
            target = sp["target"]
            unit = sp["unit"]

            try:
                node = client.get_node(node_id)
                current_val = await node.read_value()
                current_float = round(float(current_val), 2)
                target_float = round(float(target), 2)

                if mode == "read":
                    status = "OK"
                elif current_float == target_float:
                    status = "MATCH (In Sync)"
                    match_count += 1
                elif mode == "dry-run":
                    status = "WOULD UPDATE"
                else:  # mode == "write"
                    dv = ua.DataValue(ua.Variant(float(target), ua.VariantType.Float))
                    await node.write_value(dv)
                    # Verify write
                    new_val = await node.read_value()
                    if round(float(new_val), 2) == target_float:
                        status = "UPDATED & VERIFIED"
                        current_float = round(float(new_val), 2)
                        updated_count += 1
                    else:
                        status = "WRITE FAILED"

                current_str = f"{current_float:+.1f} {unit}"
                target_str = f"{target_float:+.1f} {unit}"
                results.append({
                    "name": name,
                    "node_id": node_id,
                    "current": current_float,
                    "target": target_float,
                    "unit": unit,
                    "status": status,
                })
                if not quiet or (quiet and status in ("UPDATED & VERIFIED", "WRITE FAILED")):
                    print(f"{name:<32} | {current_str:<12} | {target_str:<14} | {status}")

            except Exception as e:
                err_status = f"Node Error: {e}"
                results.append({
                    "name": name,
                    "node_id": node_id,
                    "target": target,
                    "unit": unit,
                    "status": err_status,
                })
                if not quiet:
                    print(f"{name:<32} | {'ERR':<12} | {target:+.1f} {unit:<10} | {err_status}")

        if not quiet:
            print("-" * 75)
            if mode == "write":
                print(f"[+] Summary: {updated_count} parameters updated, {match_count} already in sync.\n")
            elif mode == "dry-run":
                print(f"[*] Dry-run complete. Run without --dry-run to apply changes to PLC.\n")

        return {
            "success": True,
            "active_prefix": active_prefix,
            "updated_count": updated_count,
            "match_count": match_count,
            "results": results,
        }


def sync_equipment_to_plc(config_path: str = None, plc_url: str = DEFAULT_PLC_URL, mode: str = "write", quiet: bool = False) -> Dict[str, Any]:
    """Synchronous helper function to run OPC UA sync directly from equipment.json."""
    try:
        path, cfg = find_equipment_config(config_path)
        setpoints = extract_plc_setpoints(cfg)
        return asyncio.run(run_opc_sync(setpoints, plc_url, DEFAULT_USER, DEFAULT_PASS, mode, quiet=quiet))
    except Exception as e:
        if not quiet:
            print(f"[!] sync_equipment_to_plc failed: {e}")
        return {"success": False, "error": str(e), "updated_count": 0, "match_count": 0, "results": []}


def main():
    parser = argparse.ArgumentParser(description="Synchronize clinical limits from equipment.json into CODESYS PLC.")
    parser.add_argument("--config", "-c", help="Path to equipment.json manifest", default=None)
    parser.add_argument("--plc", "-p", help="OPC UA URL", default=DEFAULT_PLC_URL)
    parser.add_argument("--user", "-u", help="OPC UA Username", default=DEFAULT_USER)
    parser.add_argument("--password", help="OPC UA Password", default=DEFAULT_PASS)
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing to PLC")
    parser.add_argument("--read", action="store_true", help="Read and display current PLC setpoints only")

    args = parser.parse_args()

    # Determine mode
    if args.read:
        mode = "read"
    elif args.dry_run:
        mode = "dry-run"
    else:
        mode = "write"

    path, cfg = find_equipment_config(args.config)
    print(f"[*] Loaded equipment manifest from: {path}")

    setpoints = extract_plc_setpoints(cfg)
    print(f"[*] Extracted {len(setpoints)} clinical setpoints from configuration.")

    asyncio.run(run_opc_sync(setpoints, args.plc, args.user, args.password, mode))


if __name__ == "__main__":
    main()


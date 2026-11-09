#!/usr/bin/env python3
"""
LabSCADA Hardware Node Calibration Logger & Manifest Synchronizer

Logs physical calibration measurements (battery divider, analog scaling, etc.)
to the PostgreSQL audit table (CAP/CLIA compliant) and updates sites/<site>/equipment.json
so the Rust firmware build pipeline automatically compiles with the updated values.

Usage Examples:
  py scripts/log_calibration.py --node cold_storage --batt-ref 4.072 --pin-ref 2.014 --user BO --notes "Bench 2x 100k 1% divider"
  py scripts/log_calibration.py --node dewar --batt-ref 4.072 --pin-ref 2.014 --user BO
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NODE_ALIASES = {
    "cold_storage": "cold_storage_node_01",
    "cold_storage_node_01": "cold_storage_node_01",
    "fridge": "cold_storage_node_01",
    "freezer": "cold_storage_node_01",
    "dewar": "dewar_node_01",
    "dewar1": "dewar_node_01",
    "dewar_node_01": "dewar_node_01",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Log sensor node calibration to DB and equipment.json")
    parser.add_argument("--site", default="demo", help="Clinic / site slug (default: demo)")
    parser.add_argument("--node", required=True, help="Node key or alias (cold_storage, dewar, etc.)")
    parser.add_argument("--batt-ref", type=float, required=True, help="Actual battery voltage measured with multimeter (V), e.g. 4.072")
    parser.add_argument("--pin-ref", type=float, required=True, help="Voltage on ADC Pin A0 (V or mV), e.g. 2.014 or 2014")
    parser.add_argument("--user", default="BO", help="Initials or ID of technician verifying calibration")
    parser.add_argument("--notes", default="Bench multimeter calibration", help="Audit notes")
    parser.add_argument("--scada-host", default="192.168.10.133", help="SCADA database host (default: 192.168.10.133)")
    parser.add_argument("--no-db", action="store_true", help="Skip logging to PostgreSQL")
    return parser.parse_args()


def main():
    args = parse_args()
    node_key = NODE_ALIASES.get(args.node.lower(), args.node)

    # 1. Normalize voltages to integers (mV)
    batt_ref_v = round(args.batt_ref, 4)
    batt_mv = int(round(batt_ref_v * 1000.0))

    pin_raw = args.pin_ref
    pin_mv = int(round(pin_raw * 1000.0 if pin_raw < 100.0 else pin_raw))
    ratio = round(batt_mv / pin_mv, 4)

    timestamp_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("==================================================")
    print("  LabSCADA Node Calibration & Manifest Update    ")
    print("==================================================")
    print(f"  Site:          {args.site}")
    print(f"  Node Key:      {node_key}")
    print(f"  Battery Ref:   {batt_ref_v:.3f} V ({batt_mv} mV)")
    print(f"  Pin Ref:       {pin_mv / 1000.0:.3f} V ({pin_mv} mV)")
    print(f"  Scale Factor:  {batt_mv} / {pin_mv} = {ratio:.4f}")
    print(f"  Verified By:   {args.user}")
    print(f"  Timestamp:     {timestamp_iso}")
    print("--------------------------------------------------")

    # 2. Update sites/<site>/equipment.json
    manifest_path = os.path.join(REPO_ROOT, "sites", args.site, "equipment.json")
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("wireless_nodes", [])
    target_node = None
    for n in nodes:
        if n.get("key") == node_key:
            target_node = n
            break

    if not target_node:
        print(f"Error: Node '{node_key}' not found in wireless_nodes in {manifest_path}", file=sys.stderr)
        sys.exit(1)

    target_node["calibration"] = {
        "battery_scale_num": batt_mv,
        "battery_scale_den": pin_mv,
        "battery_ref_v": batt_ref_v,
        "pin_measured_mv": pin_mv,
        "calibrated_at": timestamp_iso,
        "verified_by": args.user,
        "notes": args.notes,
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    print(f"✔ Updated {manifest_path}")

    # 3. Log to PostgreSQL Audit Table
    if not args.no_db:
        slot_id = target_node.get("slot", 1)
        node_name = target_node.get("name", node_key)
        sql = f"""
        INSERT INTO mod_arc_postgre_sql.node_calibration_logs 
        (site_key, node_key, node_name, slot_id, cal_type, ref_value_v, pin_measured_mv, scale_num, scale_den, ratio, verified_by, notes)
        VALUES
        ('{args.site}', '{node_key}', '{node_name}', {slot_id}, 'battery_divider', {batt_ref_v}, {pin_mv}, {batt_mv}, {pin_mv}, {ratio}, '{args.user}', '{args.notes}');
        """
        ssh_cmd = [
            "ssh",
            f"bobostrom@{args.scada_host}",
            f'echo cycleB0b | sudo -S -u postgres psql -d rapid_scada -c "{sql.strip()}"'
        ]
        try:
            res = subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
            print("✔ Recorded entry in PostgreSQL `mod_arc_postgre_sql.node_calibration_logs`")
        except Exception as e:
            print(f"Warning: Failed to log to PostgreSQL on {args.scada_host}: {e}")

        # Sync to /etc/labscada/equipment.json
        scp_cmd = [
            "scp",
            manifest_path,
            f"bobostrom@{args.scada_host}:/tmp/equipment.json"
        ]
        sync_cmd = [
            "ssh",
            f"bobostrom@{args.scada_host}",
            "echo cycleB0b | sudo -S cp /tmp/equipment.json /etc/labscada/equipment.json"
        ]
        try:
            subprocess.run(scp_cmd, capture_output=True, text=True, check=True)
            subprocess.run(sync_cmd, capture_output=True, text=True, check=True)
            print(f"✔ Synchronized manifest to {args.scada_host}:/etc/labscada/equipment.json")
        except Exception as e:
            print(f"Warning: Failed to sync to SCADA host: {e}")

    print("--------------------------------------------------")
    print("To compile & flash with this calibration:")
    bin_name = "fridge_node" if "cold_storage" in node_key else "dewar_node"
    print(f"  cargo espflash flash --chip esp32s3 --release --bin {bin_name}")
    print("==================================================")


if __name__ == "__main__":
    main()

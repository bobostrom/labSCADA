#!/usr/bin/env python3
"""
sync_template_to_db.py
Parses Rapid SCADA DrvModbus_RTAC_Template.xml and automatically syncs tag names
to PostgreSQL table mod_arc_postgre_sql.channel_config.
"""

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

TEMPLATE_PATH = "/opt/scada/ScadaComm/Config/DrvModbus_RTAC_Template.xml"
BACKUP_PATH = "/home/bobostrom/Projects/scada/scada_config/ScadaComm/DrvModbus_RTAC_Template.xml"

# Mapping of (group_name, elem_index) -> cnl_num
GROUP_INDEX_TO_CNL = {
    "Temperatures": {
        0: 101,
        1: 102,
        2: 103,
        3: 104,
        4: 105,
        5: 106,
        6: 107,
        7: 108,
        8: 109,
        9: 110,
        10: 125,  # Embryo Storage Tank / TC Cryo
    },
    "Temperature Sensor Status": {
        0: 111,
        1: 112,
        2: 113,
        3: 114,
        4: 115,
        5: 116,
        6: 117,
        7: 118,
        8: 119,
        9: 120,
    },
    "DoorsOpen": {
        0: 121,
        1: 122,
    },
    "Incubator Alarms": {
        0: 123,
        1: 124,
    },
}


def main():
    if not os.path.isfile(TEMPLATE_PATH):
        print(f"Template file not found at {TEMPLATE_PATH}", file=sys.stderr)
        sys.exit(1)

    try:
        tree = ET.parse(TEMPLATE_PATH)
        root = tree.getroot()
    except Exception as e:
        print(f"Error parsing XML from {TEMPLATE_PATH}: {e}", file=sys.stderr)
        sys.exit(1)

    elem_groups = root.find("ElemGroups")
    if elem_groups is None:
        print("No ElemGroups found in XML", file=sys.stderr)
        sys.exit(1)

    channel_updates = {}

    for group in elem_groups.findall("ElemGroup"):
        group_name = group.get("name", "").strip()
        if group_name not in GROUP_INDEX_TO_CNL:
            continue

        mapping = GROUP_INDEX_TO_CNL[group_name]
        elems = group.findall("Elem")
        for idx, elem in enumerate(elems):
            if idx in mapping:
                cnl_num = mapping[idx]
                tag_name = elem.get("name") or elem.get("tagCode")
                if tag_name:
                    tag_name = tag_name.strip()
                    channel_updates[cnl_num] = tag_name

    if not channel_updates:
        print("No matching channels found to update.")
        return

    # Build SQL update transaction
    sql_statements = ["BEGIN;"]
    for cnl_num, name in sorted(channel_updates.items()):
        # Escape single quotes in name
        escaped_name = name.replace("'", "''")
        sql_statements.append(
            f"UPDATE mod_arc_postgre_sql.channel_config SET name = '{escaped_name}' WHERE cnl_num = {cnl_num};"
        )
    sql_statements.append("COMMIT;")
    batch_sql = "\n".join(sql_statements)

    env = os.environ.copy()
    env["PGPASSWORD"] = "postgres"
    result = subprocess.run(
        [
            "psql",
            "-h",
            "localhost",
            "-U",
            "postgres",
            "-d",
            "rapid_scada",
            "-q",
            "-c",
            batch_sql,
        ],
        env=env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Error updating PostgreSQL: {result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)

    # Also keep repository backup in sync
    try:
        os.makedirs(os.path.dirname(BACKUP_PATH), exist_ok=True)
        shutil.copy2(TEMPLATE_PATH, BACKUP_PATH)
    except Exception as e:
        print(f"Warning: Could not copy template to backup path: {e}", file=sys.stderr)

    print(f"Successfully synced {len(channel_updates)} channels from template to PostgreSQL:")
    for cnl_num, name in sorted(channel_updates.items()):
        if cnl_num in (101, 102, 103, 125):
            print(f"  - Channel {cnl_num}: '{name}'")


if __name__ == "__main__":
    main()

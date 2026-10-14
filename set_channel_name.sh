#!/usr/bin/env bash
# ==============================================================================
# set_channel_name.sh
# Updates sensor channel names in the PostgreSQL single-source-of-truth table.
# Both Grafana gauges and trend charts automatically reflect this name.
# ==============================================================================
set -e

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <cnl_num> \"<new_name>\""
    echo "Example: $0 125 \"Embryo Tank 1\""
    exit 1
fi

CNL="$1"
NAME="$2"

PGPASSWORD=postgres psql -h localhost -U postgres -d rapid_scada -q -c "
UPDATE mod_arc_postgre_sql.channel_config 
SET name = '$NAME' 
WHERE cnl_num = $CNL;
"

echo "Successfully updated Channel $CNL name to: \"$NAME\""
echo "Grafana gauges and trend charts will reflect this on their next refresh."

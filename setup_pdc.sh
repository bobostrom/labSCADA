#!/usr/bin/env bash
set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <PDC_TOKEN> [CLUSTER] [HOSTED_GRAFANA_ID]"
    echo "Example: $0 glc_eyJ... prod-us-west-0 1872512"
    exit 1
fi

TOKEN="$1"
CLUSTER="${2:-prod-us-west-0}"
GRAFANA_ID="${3:-1872512}"

echo "=== Configuring Grafana Cloud PDC Agent ==="
echo "Cluster: $CLUSTER"
echo "Grafana ID: $GRAFANA_ID"

cat > /etc/systemd/system/pdc-agent.service << EOF
[Unit]
Description=Grafana Cloud Private Data Connect (PDC) Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=bobostrom
ExecStart=/usr/local/bin/pdc \\
  -token "$TOKEN" \\
  -cluster "$CLUSTER" \\
  -gcloud-hosted-grafana-id "$GRAFANA_ID"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now pdc-agent.service
systemctl status pdc-agent.service --no-pager
echo "PDC Agent successfully configured and started!"

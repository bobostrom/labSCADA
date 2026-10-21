#!/usr/bin/env bash
set -e

echo "=== 1. Writing Datasource Provisioning ==="
mkdir -p /etc/grafana/provisioning/datasources
cat > /etc/grafana/provisioning/datasources/rapid_scada.yaml << 'EOF'
apiVersion: 1

datasources:
  - name: "PostgreSQL - SCADAPi02"
    type: postgres
    uid: "postgres-scadapi02"
    access: proxy
    url: 127.0.0.1:5432
    user: grafana_reader
    secureJsonData:
      password: "scada"
    jsonData:
      database: "rapid_scada"
      sslmode: "disable"
      postgresVersion: 1700
      timescaledb: false
    isDefault: true
    editable: true
EOF

echo "=== 2. Writing Dashboard Provisioning ==="
mkdir -p /etc/grafana/provisioning/dashboards
cat > /etc/grafana/provisioning/dashboards/ivf_lab.yaml << 'EOF'
apiVersion: 1

providers:
  - name: 'IVF Lab'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: false
EOF

mkdir -p /var/lib/grafana/dashboards
cp /home/bobostrom/Projects/labSCADA/grafana_ivf_lab_dashboard.json /var/lib/grafana/dashboards/
chown -R grafana:grafana /var/lib/grafana/dashboards

echo "=== 3. Enabling Anonymous Viewer Access in grafana.ini ==="
sed -i 's/^;enabled = false/enabled = true/' /etc/grafana/grafana.ini || true
# Explicitly append auth.anonymous configuration if not present
if ! grep -q "\[auth.anonymous\]" /etc/grafana/grafana.ini; then
    cat >> /etc/grafana/grafana.ini << 'EOF'

[auth.anonymous]
enabled = true
org_name = Main Org.
org_role = Viewer
EOF
else
    # Update existing section
    sed -i '/\[auth.anonymous\]/,/\[/{s/^[; ]*enabled = .*/enabled = true/}' /etc/grafana/grafana.ini
fi

echo "=== 4. Starting and Enabling grafana-server ==="
systemctl daemon-reload
systemctl enable grafana-server
systemctl restart grafana-server

# Set admin password to cycleB0b
sleep 3
grafana-cli admin reset-admin-password cycleB0b || true

echo "=== 5. Health Check ==="
systemctl is-active grafana-server

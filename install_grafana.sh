#!/usr/bin/env bash
set -e

echo "=== 1. Setting up Grafana APT Repository ==="
mkdir -p -m 755 /etc/apt/keyrings
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor --yes -o /etc/apt/keyrings/grafana.gpg
chmod 644 /etc/apt/keyrings/grafana.gpg
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" > /etc/apt/sources.list.d/grafana.list

echo "=== 2. Updating package list and installing Grafana ==="
apt-get update -y
apt-get install -y grafana

echo "=== 3. Configuring PostgreSQL Datasource Provisioning ==="
mkdir -p /etc/grafana/provisioning/datasources
cat > /etc/grafana/provisioning/datasources/rapid_scada.yaml << 'EOF'
apiVersion: 1

datasources:
  - name: "PostgreSQL - SCADAPi02 (Local)"
    type: postgres
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

echo "=== 4. Configuring Dashboard Provisioning ==="
mkdir -p /etc/grafana/provisioning/dashboards
cat > /etc/grafana/provisioning/dashboards/ivf_lab.yaml << 'EOF'
apiVersion: 1

providers:
  - name: 'IVF Lab Dashboards'
    orgId: 1
    folder: 'IVF Telemetry'
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

echo "=== 5. Enabling and Starting Grafana Service ==="
systemctl daemon-reload
systemctl enable grafana-server
systemctl restart grafana-server

echo "=== 6. Verifying Grafana Status ==="
systemctl is-active grafana-server
echo "Grafana installation and provisioning complete!"

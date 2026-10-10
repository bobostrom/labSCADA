#!/usr/bin/env bash
# ==============================================================================
# deploy_scada_config.sh
# Deploys version-controlled configuration from scada_config/ into /opt/scada
# and restarts Rapid SCADA services.
# ==============================================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$REPO_DIR/scada_config"

if [ ! -d "$CONFIG_DIR" ]; then
    echo "Error: Configuration directory $CONFIG_DIR not found!"
    exit 1
fi

echo "=== Deploying configuration to /opt/scada ==="

# 1. BaseDAT
if [ -d "$CONFIG_DIR/BaseDAT" ]; then
    echo "-> Deploying BaseDAT..."
    sudo mkdir -p /opt/scada/BaseDAT
    sudo cp "$CONFIG_DIR/BaseDAT/"*.dat /opt/scada/BaseDAT/
fi

# 2. ScadaComm
if [ -d "$CONFIG_DIR/ScadaComm" ]; then
    echo "-> Deploying ScadaComm..."
    sudo mkdir -p /opt/scada/ScadaComm/Config /opt/scada/Config /opt/scada/ScadaComm/Config/DrvModbus
    sudo cp "$CONFIG_DIR/ScadaComm/"*.xml /opt/scada/ScadaComm/Config/
    # Mirror template files if present
    if [ -f "$CONFIG_DIR/ScadaComm/RTAC_Modbus.xml" ]; then
        sudo cp "$CONFIG_DIR/ScadaComm/RTAC_Modbus.xml" /opt/scada/Config/
        sudo cp "$CONFIG_DIR/ScadaComm/RTAC_Modbus.xml" /opt/scada/ScadaComm/Config/DrvModbus/
    fi
fi

# 3. ScadaServer
if [ -f "$CONFIG_DIR/ScadaServer/ScadaServerConfig.xml" ]; then
    echo "-> Deploying ScadaServer..."
    sudo mkdir -p /opt/scada/ScadaServer/Config
    sudo cp "$CONFIG_DIR/ScadaServer/ScadaServerConfig.xml" /opt/scada/ScadaServer/Config/
fi

# 4. ScadaWeb
if [ -f "$CONFIG_DIR/ScadaWeb/ScadaWebConfig.xml" ]; then
    echo "-> Deploying ScadaWeb..."
    sudo mkdir -p /opt/scada/ScadaWeb/config
    sudo cp "$CONFIG_DIR/ScadaWeb/ScadaWebConfig.xml" /opt/scada/ScadaWeb/config/
fi

# 5. Views
if [ -d "$CONFIG_DIR/Views" ]; then
    echo "-> Deploying Views..."
    sudo mkdir -p /opt/scada/Views
    sudo cp -r "$CONFIG_DIR/Views/"* /opt/scada/Views/
fi

# Ensure user ownership for ease of use
sudo chown -R bobostrom:bobostrom /opt/scada

echo "=== Restarting Rapid SCADA services ==="
sudo systemctl restart scadaserver6 scadacomm6 scadaweb6

echo "=== Deployment Complete! ==="

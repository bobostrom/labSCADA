#!/usr/bin/env bash
# ==============================================================================
# backup_scada_config.sh
# Pulls the active Rapid SCADA configuration from /opt/scada into the repository
# ==============================================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$REPO_DIR/scada_config"

echo "=== Pulling Rapid SCADA configuration into $CONFIG_DIR ==="

mkdir -p "$CONFIG_DIR/BaseDAT" \
         "$CONFIG_DIR/ScadaComm" \
         "$CONFIG_DIR/ScadaServer" \
         "$CONFIG_DIR/ScadaWeb" \
         "$CONFIG_DIR/Views"

# 1. BaseDAT (Configuration Database)
echo "-> Backing up BaseDAT (.dat files)..."
cp /opt/scada/BaseDAT/*.dat "$CONFIG_DIR/BaseDAT/"

# 2. ScadaComm
echo "-> Backing up ScadaComm configuration..."
cp /opt/scada/ScadaComm/Config/*.xml "$CONFIG_DIR/ScadaComm/"

# 3. ScadaServer
echo "-> Backing up ScadaServer configuration..."
cp /opt/scada/ScadaServer/Config/ScadaServerConfig.xml "$CONFIG_DIR/ScadaServer/"

# 4. ScadaWeb
echo "-> Backing up ScadaWeb configuration..."
cp /opt/scada/ScadaWeb/config/ScadaWebConfig.xml "$CONFIG_DIR/ScadaWeb/"

# 5. Views
echo "-> Backing up Views..."
cp -r /opt/scada/Views/* "$CONFIG_DIR/Views/"

echo "=== Successfully updated $CONFIG_DIR ==="
echo "Run 'git status' and 'git diff' to review changes, then commit when ready."

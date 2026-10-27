#!/usr/bin/env bash
# ==============================================================================
# deploy_site.sh [site_name]
# Activates a site manifest (e.g. 'afoa' or 'demo') on the local SCADA host:
# 1. Validates sites/<site_name>/site.env exists
# 2. Deploys to /etc/labscada/site.env
# 3. Restarts ivf-alert-engine.service
# ==============================================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SITE="$1"

if [ -z "$SITE" ]; then
    echo "Usage: ./deploy_site.sh [afoa|demo|<site_name>]"
    echo "Available sites in $REPO_DIR/sites/:"
    ls -d "$REPO_DIR"/sites/*/ 2>/dev/null | xargs -n 1 basename
    exit 1
fi

SITE_DIR="$REPO_DIR/sites/$SITE"
SOURCE_ENV="$SITE_DIR/site.env"

if [ ! -f "$SOURCE_ENV" ]; then
    echo "Error: Site manifest not found at $SOURCE_ENV"
    exit 1
fi

echo "=== Activating Site: $SITE ==="
sudo mkdir -p /etc/labscada

echo "-> Installing $SOURCE_ENV to /etc/labscada/site.env..."
sudo cp "$SOURCE_ENV" /etc/labscada/site.env
sudo chmod 644 /etc/labscada/site.env

# Also keep a local site.env symlink or copy for local non-root development
cp "$SOURCE_ENV" "$REPO_DIR/site.env"

# Deploy site-specific Rapid SCADA configuration (e.g. WAGO vs Raspberry Pi OPC UA mappings)
if [ -d "$SITE_DIR/scada_config" ]; then
    echo "-> Deploying site-specific Rapid SCADA configs from $SITE_DIR/scada_config..."
    sudo cp "$SITE_DIR/scada_config/"*.xml /opt/scada/ScadaComm/Config/ 2>/dev/null || true
    if systemctl is-active --quiet scadacomm6.service 2>/dev/null; then
        echo "-> Restarting scadacomm6.service..."
        sudo systemctl restart scadacomm6.service
        echo "✅ scadacomm6 restarted with $SITE configuration!"
    fi
fi

echo "-> Restarting ivf-alert-engine.service..."
if systemctl is-active --quiet ivf-alert-engine.service 2>/dev/null; then
    sudo systemctl restart ivf-alert-engine.service
    echo "✅ ivf-alert-engine restarted successfully!"
else
    echo "ℹ️ ivf-alert-engine service is not currently active. Start with: sudo systemctl start ivf-alert-engine"
fi

echo "=== Site Activation Complete: $SITE ==="


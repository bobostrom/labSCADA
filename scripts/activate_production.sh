#!/bin/bash
set -e
echo "=== Activating WAGO 752 as Production afoa-scada ==="

echo "1. Enabling and starting IVF Alert Engine..."
systemctl enable --now ivf-alert-engine

echo "2. Enabling and starting Cloudflare Zero Trust Tunnel..."
systemctl enable --now cloudflared

echo "3. Verifying service status..."
for s in postgresql scadaserver6 scadacomm6 scadaweb6 scadaagent6 ivf-alert-engine cloudflared; do
    echo -n "  - ${s}: "
    systemctl is-active "${s}"
done

echo "=== WAGO 752 SCADA System Active & Live ==="


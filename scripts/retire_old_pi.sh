#!/bin/bash
set -e
echo "=== Retiring Old SCADA Pi (afoa-scada -> afoa-scada-og) ==="

echo "1. Stopping and disabling all SCADA services..."
sudo systemctl stop cloudflared ivf-alert-engine scadacomm6 scadaserver6 scadaweb6 scadaagent6 2>/dev/null || true
sudo systemctl disable cloudflared ivf-alert-engine scadacomm6 scadaserver6 scadaweb6 scadaagent6 2>/dev/null || true

echo "2. Updating hostname to afoa-scada-og..."
sudo hostnamectl set-hostname afoa-scada-og

echo "3. Updating /etc/hosts..."
sudo sed -i 's/afoa-scada/afoa-scada-og/g' /etc/hosts

echo "=== Old Pi Decommissioned Successfully ==="
echo "Change the MikroTik DHCP lease for 2C:CF:67:ED:38:CF to 192.168.88.250, then reboot."


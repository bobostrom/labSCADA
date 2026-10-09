#!/usr/bin/env bash
set -e

echo "=== Copying RTAC Modbus configuration to Rapid SCADA ==="
sudo cp /home/bobostrom/Projects/scada/RTAC_Modbus.xml /opt/scada/ScadaComm/Config/
sudo cp /home/bobostrom/Projects/scada/ScadaCommConfig.xml /opt/scada/ScadaComm/Config/

# Also place template in root Config and DrvModbus if looked up there
sudo mkdir -p /opt/scada/Config /opt/scada/ScadaComm/Config/DrvModbus
sudo cp /home/bobostrom/Projects/scada/RTAC_Modbus.xml /opt/scada/Config/
sudo cp /home/bobostrom/Projects/scada/RTAC_Modbus.xml /opt/scada/ScadaComm/Config/DrvModbus/

# Allow bobostrom ownership so subsequent edits don't need sudo
sudo chown -R bobostrom:bobostrom /opt/scada

echo "=== Restarting ScadaComm service ==="
sudo systemctl restart scadacomm6

echo "=== Done! ==="

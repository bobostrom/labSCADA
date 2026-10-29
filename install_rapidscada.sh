#!/usr/bin/env bash
# ==============================================================================
# install_rapidscada.sh
# Automated Installer & Service Provisioner for IVF Lab SCADA System
# Compatible with Debian / Ubuntu (ARM64 & x86_64 / AMD64)
# ==============================================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_USER="${SUDO_USER:-$(whoami)}"

echo "=== [1/8] Configuring Hardware RTC & Disabling fake-hwclock ==="
if dpkg -s fake-hwclock >/dev/null 2>&1; then
    sudo apt purge -y fake-hwclock
    sudo update-rc.d -f fake-hwclock remove || true
fi
sudo systemctl enable --now systemd-timesyncd || true
# Sync system time to battery-backed RTC if clock is valid
sudo hwclock -w || echo "Notice: Check if RTC I2C overlay is needed in /boot/firmware/config.txt"

echo "=== [2/8] Updating System & Installing Prerequisites ==="
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl wget unzip tar libssl-dev libicu-dev nginx git \
    postgresql postgresql-contrib \
    python3 python3-pip python3-jinja2 python3-psycopg2 python3-matplotlib python3-pil python3-opcua

echo "=== [3/8] Installing ASP.NET Core Runtime (.NET 10) ==="
# Detect architecture (supports both Raspberry Pi ARM64 and WAGO x86_64)
RAW_ARCH=$(uname -m)
case "$RAW_ARCH" in
    x86_64)
        DOTNET_ARCH="x64"
        ;;
    aarch64|arm64)
        DOTNET_ARCH="arm64"
        ;;
    armv7l|armhf)
        DOTNET_ARCH="arm"
        ;;
    *)
        DOTNET_ARCH="$RAW_ARCH"
        ;;
esac
echo "Detected system architecture: $RAW_ARCH (using .NET runtime arch: $DOTNET_ARCH)"

curl -sSL https://dot.net/v1/dotnet-install.sh | sudo bash /dev/stdin \
    --runtime aspnetcore \
    --channel 10.0 \
    --architecture "$DOTNET_ARCH" \
    --install-dir /usr/share/dotnet

sudo ln -sf /usr/share/dotnet/dotnet /usr/bin/dotnet
echo "Dotnet verified: $(dotnet --version) ($(uname -m))"

echo "=== [4/8] Setting Up Persistent Logging Directory ==="
sudo mkdir -p /var/log/scada
sudo chmod 755 /var/log/scada

echo "=== [5/8] Deploying Rapid SCADA 6 Package ==="
sudo mkdir -p /opt/scada

# Check for local archive in current directory, ~/rapidscada_install, or /tmp
PACKAGE_DEB=$(ls "$REPO_DIR"/rapidscada_*.deb ~/rapidscada_install/rapidscada_*.deb /tmp/rapidscada_*.deb 2>/dev/null | head -n 1 || true)
PACKAGE_ZIP=$(ls "$REPO_DIR"/rapidscada_*.zip ~/rapidscada_install/rapidscada_*.zip /tmp/rapidscada_*.zip 2>/dev/null | head -n 1 || true)

if [ -z "$PACKAGE_DEB" ] && [ -z "$PACKAGE_ZIP" ] && [ ! -d "/opt/scada/ScadaServer" ]; then
    echo "No package found locally. Downloading Rapid SCADA 6.5.0 for Linux (.NET 10)..."
    wget -q --show-progress -O "$REPO_DIR/rapidscada_6.5.0_linux_en.zip" https://rapidscada.org/download/rapidscada_6.5.0_linux_en.zip
    PACKAGE_ZIP="$REPO_DIR/rapidscada_6.5.0_linux_en.zip"
fi

if [ -n "$PACKAGE_DEB" ]; then
    echo "Found deb package: $PACKAGE_DEB. Installing..."
    sudo dpkg -i "$PACKAGE_DEB"
elif [ -n "$PACKAGE_ZIP" ]; then
    if unzip -l "$PACKAGE_ZIP" | grep -q "rapidscada_.*\.deb"; then
        echo "Extracting bundled .deb from $PACKAGE_ZIP..."
        mkdir -p /tmp/scada_extract
        unzip -q -o "$PACKAGE_ZIP" "*.deb" -d /tmp/scada_extract
        DEB_FILE=$(ls /tmp/scada_extract/*.deb 2>/dev/null | head -n 1)
        sudo dpkg -i "$DEB_FILE"
        rm -rf /tmp/scada_extract
    else
        echo "Found zip package: $PACKAGE_ZIP. Extracting..."
        mkdir -p /tmp/scada_extract
        unzip -q -o "$PACKAGE_ZIP" -d /tmp/scada_extract
        if [ -d "/tmp/scada_extract/scada" ]; then
            sudo cp -r /tmp/scada_extract/scada/* /opt/scada/
        else
            sudo cp -r /tmp/scada_extract/* /opt/scada/
        fi
        if [ -d "/tmp/scada_extract/daemons" ]; then
            sudo cp /tmp/scada_extract/daemons/*.service /etc/systemd/system/
        fi
        rm -rf /tmp/scada_extract
    fi
elif [ -d "/opt/scada/ScadaServer" ]; then
    echo "Rapid SCADA files already found in /opt/scada."
fi

# Set executable bits if scripts exist
if [ -f "/opt/scada/make_executable.sh" ]; then
    sudo chmod +x /opt/scada/make_executable.sh
    sudo /opt/scada/make_executable.sh
fi

# Deploy version-controlled SCADA configuration (BaseDAT, ScadaComm, ScadaServer, OPC UA)
if [ -f "$REPO_DIR/deploy_scada_config.sh" ]; then
    echo "Deploying version-controlled SCADA configuration..."
    bash "$REPO_DIR/deploy_scada_config.sh"
else
    sudo chown -R "${CURRENT_USER}:${CURRENT_USER}" /opt/scada
fi

echo "=== [6/8] Provisioning PostgreSQL Database & Schemas ==="
sudo systemctl enable --now postgresql

# Create rapid_scada database if it doesn't exist
if ! sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = 'rapid_scada'" | grep -q 1; then
    echo "Creating database rapid_scada..."
    sudo -u postgres psql -c "CREATE DATABASE rapid_scada;"
fi

# Ensure mod_arc_postgre_sql schema exists
sudo -u postgres psql -d rapid_scada -c "CREATE SCHEMA IF NOT EXISTS mod_arc_postgre_sql;"

# Apply channel configuration and alarm events table
if [ -f "$REPO_DIR/setup_channel_config.sql" ]; then
    echo "Applying channel configuration and alarm events schema..."
    sudo -u postgres psql -d rapid_scada -f "$REPO_DIR/setup_channel_config.sql"
fi

# Apply LN2 tracking table
if [ -f "$REPO_DIR/setup_ln2_tracking.sql" ]; then
    echo "Applying LN2 tracking tables..."
    sudo -u postgres psql -d rapid_scada -f "$REPO_DIR/setup_ln2_tracking.sql"
fi

# Apply Session lifecycle, cleanroom door events, and maintenance holds
if [ -f "$REPO_DIR/setup_session_and_audit.sql" ]; then
    echo "Applying session lifecycle and door audit schema..."
    sudo -u postgres psql -d rapid_scada -f "$REPO_DIR/setup_session_and_audit.sql"
fi

# Ensure /etc/labscada/db.env exists
sudo mkdir -p /etc/labscada
if [ ! -f "/etc/labscada/db.env" ] && [ -f "$REPO_DIR/db.env.example" ]; then
    sudo cp "$REPO_DIR/db.env.example" /etc/labscada/db.env
    echo "Created /etc/labscada/db.env from template."
fi

echo "=== [7/8] Configuring Nginx Reverse Proxy & Web Assets ==="
# Generate self-signed certificate if missing
if [ ! -f "/etc/ssl/certs/nginx-selfsigned.crt" ] || [ ! -f "/etc/ssl/private/nginx-selfsigned.key" ]; then
    echo "Generating self-signed SSL certificate for Nginx..."
    sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/ssl/private/nginx-selfsigned.key \
        -out /etc/ssl/certs/nginx-selfsigned.crt \
        -subj "/C=US/ST=Alaska/L=Anchorage/O=AdvancedFertility/CN=$(hostname)"
fi

if [ -f "$REPO_DIR/nginx/default" ]; then
    sudo cp "$REPO_DIR/nginx/default" /etc/nginx/sites-available/default
elif [ -f "/opt/scada/nginx/default" ]; then
    sudo cp /opt/scada/nginx/default /etc/nginx/sites-available/default
fi

# Deploy favicon to webroot
sudo mkdir -p /var/www/html
if [ -f "$REPO_DIR/assets/favicon.ico" ]; then
    sudo cp "$REPO_DIR/assets/favicon.ico" /var/www/html/favicon.ico
elif [ -f "$REPO_DIR/notes/assets/favicon.ico" ]; then
    sudo cp "$REPO_DIR/notes/assets/favicon.ico" /var/www/html/favicon.ico
fi

sudo nginx -t
sudo systemctl restart nginx

echo "=== [8/8] Registering & Starting Systemd Services ==="
# Register Rapid SCADA daemons
if ls /opt/scada/daemons/*.service 1> /dev/null 2>&1; then
    sudo cp /opt/scada/daemons/*.service /etc/systemd/system/
fi

# Register IVF Alert Engine & Kiosk service
if [ -f "$REPO_DIR/ivf-alert-engine.service" ]; then
    echo "Configuring and enabling ivf-alert-engine.service for user $CURRENT_USER in $REPO_DIR..."
    sudo sed -e "s|User=.*|User=$CURRENT_USER|" \
             -e "s|WorkingDirectory=.*|WorkingDirectory=$REPO_DIR|" \
             -e "s|ExecStart=.*|ExecStart=/usr/bin/python3 $REPO_DIR/ivf_alert_engine.py|" \
             "$REPO_DIR/ivf-alert-engine.service" > /tmp/ivf-alert-engine.service
    sudo cp /tmp/ivf-alert-engine.service /etc/systemd/system/ivf-alert-engine.service
    rm -f /tmp/ivf-alert-engine.service
fi

# Stop/disable legacy conflicting dashboard service if active
if systemctl is-active --quiet ivf-dashboard 2>/dev/null; then
    sudo systemctl stop ivf-dashboard || true
fi
if systemctl is-enabled --quiet ivf-dashboard 2>/dev/null; then
    sudo systemctl disable ivf-dashboard || true
fi

sudo systemctl daemon-reload
sudo systemctl enable scadaagent6 scadaserver6 scadacomm6 scadaweb6 ivf-alert-engine
sudo systemctl restart scadaserver6 scadacomm6 scadaweb6 scadaagent6 ivf-alert-engine || true

HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$HOST_IP" ] && HOST_IP="127.0.0.1"

echo ""
echo "=========================================================="
echo "🎉 IVF Lab SCADA Installation Complete!"
echo "----------------------------------------------------------"
echo "Touchscreen Kiosk (Live Ops):   http://${HOST_IP}/"
echo "Cryo Tank Audit Suite:          http://${HOST_IP}/cryo"
echo "Monthly Compliance Report:      http://${HOST_IP}/report/ln2"
echo "Mobile QR LN2 Dipstick Log:     http://${HOST_IP}/log"
echo "Printable Station QR Placard:   http://${HOST_IP}/print/qr"
echo "Rapid SCADA Webstation:         http://${HOST_IP}/scada/ (admin / scada)"
echo "----------------------------------------------------------"
echo "System Daemons: scadaserver6, scadacomm6, scadaweb6, ivf-alert-engine"
echo "=========================================================="

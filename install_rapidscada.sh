#!/usr/bin/env bash
set -e

echo "=== [1/7] Configuring Hardware RTC & Disabling fake-hwclock ==="
if dpkg -s fake-hwclock >/dev/null 2>&1; then
    sudo apt purge -y fake-hwclock
    sudo update-rc.d -f fake-hwclock remove || true
fi
sudo systemctl enable --now systemd-timesyncd || true
# Sync system time to battery-backed RTC if clock is valid
sudo hwclock -w || echo "Notice: Check if RTC I2C overlay is needed in /boot/firmware/config.txt"

echo "=== [2/7] Updating System & Installing Prerequisites ==="
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl wget unzip tar libssl-dev libicu-dev nginx

echo "=== [3/7] Installing ASP.NET Core Runtime (.NET 8 ARM64) ==="
curl -sSL https://dot.net/v1/dotnet-install.sh | sudo bash /dev/stdin \
    --runtime aspnetcore \
    --channel 8.0 \
    --architecture arm64 \
    --install-dir /usr/share/dotnet

sudo ln -sf /usr/share/dotnet/dotnet /usr/bin/dotnet
echo "Dotnet verified: $(dotnet --version) ($(uname -m))"

echo "=== [4/7] Setting Up Persistent Logging on NVMe SSD ==="
sudo mkdir -p /var/log/scada
sudo chmod 755 /var/log/scada

echo "=== [5/7] Deploying Rapid SCADA 6 Package ==="
sudo mkdir -p /opt/scada

# Check for local archive in current directory or /tmp
PACKAGE_DEB=$(ls ./rapidscada_*.deb /tmp/rapidscada_*.deb 2>/dev/null | head -n 1 || true)
PACKAGE_ZIP=$(ls ./rapidscada_*.zip /tmp/rapidscada_*.zip 2>/dev/null | head -n 1 || true)

if [ -z "$PACKAGE_DEB" ] && [ -z "$PACKAGE_ZIP" ] && [ ! -d "/opt/scada/ScadaServer" ]; then
    echo "No package found locally. Downloading Rapid SCADA 6.4.7 for Linux (.NET 8)..."
    wget -q --show-progress -O ./rapidscada_6.4.7_linux_en.zip https://rapidscada.org/download/rapidscada_6.4.7_linux_en.zip
    PACKAGE_ZIP="./rapidscada_6.4.7_linux_en.zip"
fi

if [ -n "$PACKAGE_DEB" ]; then
    echo "Found deb package: $PACKAGE_DEB. Installing..."
    sudo dpkg -i "$PACKAGE_DEB"
elif [ -n "$PACKAGE_ZIP" ]; then
    # Extract bundled .deb if present in the zip
    if unzip -l "$PACKAGE_ZIP" | grep -q "rapidscada_.*\.deb"; then
        echo "Extracting bundled .deb from $PACKAGE_ZIP..."
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
sudo chown -R root:root /opt/scada

echo "=== [6/7] Configuring Nginx Reverse Proxy ==="
# Generate self-signed certificate if missing
if [ ! -f "/etc/ssl/certs/nginx-selfsigned.crt" ] || [ ! -f "/etc/ssl/private/nginx-selfsigned.key" ]; then
    echo "Generating self-signed SSL certificate for Nginx..."
    sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/ssl/private/nginx-selfsigned.key \
        -out /etc/ssl/certs/nginx-selfsigned.crt \
        -subj "/C=US/ST=State/L=City/O=SCADA/CN=$(hostname)"
fi

if [ -f "./nginx/default" ]; then
    sudo cp ./nginx/default /etc/nginx/sites-available/default
elif [ -f "/opt/scada/nginx/default" ]; then
    sudo cp /opt/scada/nginx/default /etc/nginx/sites-available/default
else
    sudo bash -c 'cat << "NGINX_EOF" > /etc/nginx/sites-available/default
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location / {
        proxy_pass         http://127.0.0.1:10008;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection keep-alive;
        proxy_set_header   Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
NGINX_EOF'
fi

sudo nginx -t
sudo systemctl restart nginx

echo "=== [7/7] Registering & Starting Systemd Services ==="
if ls /opt/scada/daemons/*.service 1> /dev/null 2>&1; then
    sudo cp /opt/scada/daemons/*.service /etc/systemd/system/
fi
sudo systemctl daemon-reload
sudo systemctl enable scadaagent6 scadaserver6 scadacomm6 scadaweb6
sudo systemctl restart scadaserver6 scadacomm6 scadaweb6 scadaagent6 || true

echo ""
echo "=========================================================="
echo "Installation complete!"
echo "Local IP: $(hostname -I | awk '{print $1}')"
echo "Web UI:   http://$(hostname -I | awk '{print $1}')"
echo "Login:    admin / scada"
echo "=========================================================="

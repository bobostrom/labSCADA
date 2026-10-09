# Rapid SCADA Linux / Raspberry Pi Deployment

Automated installer and service configuration for deploying [Rapid SCADA](https://rapidscada.org) on Linux (Debian / Ubuntu / Raspberry Pi OS ARM64 & AMD64) with ASP.NET Core Runtime and Nginx reverse proxy.

## Architecture & Features

- **Hardware RTC support:** Disables `fake-hwclock` and enables battery-backed RTC sync (`hwclock` / `systemd-timesyncd`).
- **Runtime Environment:** Automated installation of ASP.NET Core Runtime 8.0 (.NET 8).
- **Automated Deployment:** Downloads and installs Rapid SCADA 6 package (`rapidscada_*.deb` / `.zip`).
- **Nginx Reverse Proxy:** Preconfigured proxy for Rapid SCADA Webstation on port `10008` (HTTP on port 80 & HTTPS with self-signed SSL on port 443).
- **Systemd Management:** Automatically registers and manages services:
  - `scadaserver6.service` - Rapid SCADA Server
  - `scadacomm6.service` - Rapid SCADA Communicator
  - `scadaweb6.service` - Rapid SCADA Webstation
  - `scadaagent6.service` - Rapid SCADA Agent

## Installation

Run the installation script:

```bash
chmod +x install_rapidscada.sh
./install_rapidscada.sh
```

Once installed, access the web interface in your browser:

- **URL:** `http://<server-ip>` or `https://<server-ip>`
- **Default Login:** `admin` / `scada`

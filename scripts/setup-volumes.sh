#!/bin/bash
# Setup initial files in volumes if they don't exist

echo "🔧 Setting up volume directories..."

# Setup TFTP directory with iPXE binaries
if [ ! -f "/srv/tftp/undionly.kpxe" ]; then
    echo "📁 Setting up TFTP directory..."
    cp -r /app/initial-files/tftp/* /srv/tftp/ 2>/dev/null || true
    echo "✅ iPXE binaries copied to /srv/tftp/"
fi

# Create initial directory structure
mkdir -p /srv/http/ubuntu-samples
mkdir -p /srv/ipxe
mkdir -p /srv/dhcp

# Create README files if they don't exist
if [ ! -f "/srv/http/README.txt" ]; then
    cat > /srv/http/README.txt << 'EOFREADME'
# HTTP Boot Resources - Multi-Version Support

This directory contains bootable images and resources served over HTTP.

## Directory Structure:
```bash
/srv/http/
├── ubuntu-20.04/          # Ubuntu 20.04 LTS files
│   ├── vmlinuz
│   ├── initrd
│   └── preseed.cfg
├── ubuntu-22.04/          # Ubuntu 22.04 LTS files
│   ├── vmlinuz
│   ├── initrd
│   └── preseed.cfg
├── ubuntu-24.04/          # Ubuntu 24.04 LTS files
│   ├── vmlinuz
│   ├── initrd
│   └── preseed.cfg
├── custom-os/             # Custom OS files
│   ├── vmlinuz
│   └── initrd
└── iso/                   # ISO images storage
    ├── ubuntu-22.04.iso
    └── ubuntu-24.04.iso
```

## Volume Mount Information:
- Container path: /srv/http
- Recommended host path: ./data/srv/http
- Purpose: HTTP-served boot files and OS images

## Usage:
- Download Ubuntu versions using the web interface
- Each version gets its own directory
- Files are persistent across container restarts
- Large files (ISOs) don't increase container size
EOFREADME
fi

if [ ! -f "/srv/tftp/README.txt" ]; then
    cat > /srv/tftp/README.txt << 'EOFREADME'
# TFTP Boot Files

This directory contains files served via TFTP for PXE boot.

## Key Files:
- undionly.kpxe  - iPXE bootloader for most network cards
- ipxe.efi       - iPXE bootloader for UEFI systems
- ipxe.pxe       - Legacy PXE bootloader

## Volume Mount Information:
- Container path: /srv/tftp
- Recommended host path: ./data/srv/tftp
- Purpose: TFTP server root directory

## DHCP Configuration:
Configure your DHCP server with:
- Option 66 (TFTP Server): YOUR_SERVER_IP
- Option 67 (Boot Filename): undionly.kpxe
EOFREADME
fi

if [ ! -f "/srv/ipxe/README.txt" ]; then
    cat > /srv/ipxe/README.txt << 'EOFREADME'
# iPXE Configuration Files

This directory contains iPXE menu scripts and configurations.

## Key Files:
- boot.ipxe      - Main iPXE boot menu script
- *.ipxe         - Custom iPXE scripts

## Volume Mount Information:
- Container path: /srv/ipxe
- Recommended host path: ./data/srv/ipxe
- Purpose: iPXE scripts and configurations

## Usage:
- Generate menus using the web interface
- Customize iPXE scripts as needed
- Files are served via HTTP to booting clients
EOFREADME
fi

# Set proper permissions
chown -R root:root /srv/
chmod -R 755 /srv/

echo "✅ Volume setup completed"
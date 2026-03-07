#!/bin/bash
# Setup initial files in volumes if they don't exist

echo "🔧 Setting up volume directories..."

# Setup TFTP directory with iPXE binaries
if [ ! -f "/srv/tftp/undionly.kpxe" ]; then
    echo "📁 Setting up TFTP directory..."
    cp -r /opt/ipxe-initial-files/tftp/* /srv/tftp/ 2>/dev/null || true
    echo "✅ iPXE binaries copied to /srv/tftp/"
fi

# Keep alternative bootloaders in sync for existing volumes.
if [ ! -f "/srv/tftp/snponly.efi" ] && [ -f "/opt/ipxe-initial-files/tftp/snponly.efi" ]; then
    cp /opt/ipxe-initial-files/tftp/snponly.efi /srv/tftp/snponly.efi
    echo "✅ snponly.efi copied to /srv/tftp/"
fi

# Keep local memdisk fallback available for legacy ISO boot entries.
if [ ! -f "/srv/http/memdisk" ] && [ -f "/opt/ipxe-initial-files/http/memdisk" ]; then
    cp /opt/ipxe-initial-files/http/memdisk /srv/http/memdisk
    echo "✅ memdisk copied to /srv/http/"
fi

# Keep local wimboot available for WinPE-based entries (e.g. Hiren PE).
if [ ! -f "/srv/http/wimboot" ] && [ -f "/opt/ipxe-initial-files/http/wimboot" ]; then
    cp /opt/ipxe-initial-files/http/wimboot /srv/http/wimboot
    echo "✅ wimboot copied to /srv/http/"
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
├── memdisk                # Legacy ISO boot helper (syslinux memdisk)
├── wimboot                # WinPE boot helper (iPXE wimboot)
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
- snponly.efi    - UEFI iPXE using firmware SNP networking
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

# Keep host volume ownership intact (do not force root:root on mounted data).
# Only ensure readable/traversable permissions for service processes.
chmod -R u+rwX,go+rX /srv/

echo "✅ Volume setup completed"

#!/bin/bash
# setup-nfs.sh — Configure NFS server on the Docker host for iPXE Ubuntu Server PXE boot.
#
# Run once on the host machine (not inside Docker):
#   sudo bash scripts/setup-nfs.sh
#
# What it does:
#   1. Installs nfs-kernel-server
#   2. Exports data/srv/http so PXE clients can mount Ubuntu Server ISO files via NFS
#   3. Prints the nfsroot= cmdline to use in the iPXE menu entry

set -e

# Must run as root
if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash $0"
  exit 1
fi

# Resolve the absolute path to data/srv/http relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
HTTP_DIR="$PROJECT_DIR/data/srv/http"

if [[ ! -d "$HTTP_DIR" ]]; then
  echo "ERROR: $HTTP_DIR not found. Run from the project root."
  exit 1
fi

# Detect subnet from the default route interface
SUBNET=$(ip route | awk '/^default/ {print $3}' | head -1 | awk -F. '{print $1"."$2"."$3".0/24"}')
if [[ -z "$SUBNET" ]]; then
  SUBNET="192.168.0.0/24"
  echo "WARNING: Could not detect subnet, using $SUBNET"
fi

echo "==> Installing nfs-kernel-server..."
apt-get install -y nfs-kernel-server

EXPORT_LINE="$HTTP_DIR $SUBNET(ro,no_subtree_check,no_root_squash)"

# Add export only if not already present
if grep -qF "$HTTP_DIR" /etc/exports 2>/dev/null; then
  echo "==> /etc/exports already has entry for $HTTP_DIR — skipping"
else
  echo "$EXPORT_LINE" >> /etc/exports
  echo "==> Added to /etc/exports: $EXPORT_LINE"
fi

echo "==> Applying exports..."
exportfs -ra

echo "==> Enabling nfs-kernel-server..."
systemctl enable --now nfs-kernel-server

echo ""
echo "==> NFS export active. Verify with:"
echo "      showmount -e localhost"
echo ""
echo "==> Use this cmdline in your iPXE Ubuntu Server entry:"
echo ""

# Print cmdline for each ubuntu-* directory found
for DIR in "$HTTP_DIR"/ubuntu-*/; do
  VERSION=$(basename "$DIR")
  echo "      ip=dhcp boot=casper netboot=nfs nfsroot=$(hostname -I | awk '{print $1}'):$HTTP_DIR/$VERSION"
done

echo ""
echo "==> Done."

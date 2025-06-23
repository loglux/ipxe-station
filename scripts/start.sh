#!/bin/bash
set -e

echo "🚀 Starting iPXE Station..."

# Setup volumes on first run
/app/setup-volumes.sh

# Starting syslog (if not running)
if ! pgrep rsyslogd > /dev/null; then
    echo "🔧 Starting rsyslog..."
    rsyslogd
else
    echo "ℹ️ rsyslog already running"
fi

# tail logs to BG
(sleep 2; tail -f /var/log/syslog | grep tftpd) &

# Start TFTP service
echo "🔧 Starting TFTP service..."
service tftpd-hpa start

# Check services
echo "📋 Service status:"
service tftpd-hpa status || echo "⚠️ TFTP service status check failed"

# Show volume information
echo "📁 Volume mounts:"
df -h /srv/tftp /srv/http /srv/ipxe /srv/dhcp 2>/dev/null || echo "ℹ️ Volume info not available"

echo "📂 Directory contents:"
ls -la /srv/

# Start main application
echo "🌐 Starting iPXE Station web interface..."
exec python main.py
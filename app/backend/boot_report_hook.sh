#!/bin/sh
# Boot report for a live system, made by iPXE Station.
# Runs as a live-config hook early in boot, as root: fetched from the server by URL (the live system
# needs wget for that) or read from the medium (live-config.hooks=medium, over NFS). It only sets up a small job; the job runs once
# the desktop is up, collects what is below and sends it to the server that started it. Serial
# numbers and UUIDs are not collected (the server already knows the machine from the network boot).
# It never fails the boot.

REPORT_URL="__REPORT_URL__"
DELAY="__DELAY__"

ROOT="${IPXE_STATION_ROOT:-}"

[ -n "$REPORT_URL" ] || exit 0

mkdir -p "${ROOT}/etc" "${ROOT}/usr/local/bin" "${ROOT}/etc/xdg/autostart" 2>/dev/null

printf "REPORT_URL='%s'\nDELAY=%s\n" "$REPORT_URL" "$DELAY" > "${ROOT}/etc/ipxe-station-report.conf"

cat > "${ROOT}/usr/local/bin/ipxe-station-boot-report" <<'EOS'
__COLLECTOR__
EOS
chmod 755 "${ROOT}/usr/local/bin/ipxe-station-boot-report"

cat > "${ROOT}/etc/xdg/autostart/ipxe-station-boot-report.desktop" <<'EOD'
[Desktop Entry]
Type=Application
Name=iPXE Station boot report
Exec=/usr/local/bin/ipxe-station-boot-report
NoDisplay=true
EOD

exit 0

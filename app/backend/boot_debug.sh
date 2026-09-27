#!/bin/sh
# Looks at why a boot report did not arrive, and sends what it finds to the iPXE Station server.
# Changes nothing except that it runs the report job once, right now.
SERVER_URL="__SERVER_URL__"
out="$(mktemp)"

{
    echo "== kernel command line"
    tr ' ' '\n' < /proc/cmdline | grep -E 'hooks|BOOTIF|netboot|nfsroot|boot='

    echo "== hooks on the medium"
    ls -la /lib/live/mount/medium/live/config-hooks/ /run/live/medium/live/config-hooks/ 2>&1

    echo "== what the hook installed"
    ls -la /etc/xdg/autostart/ipxe-station* /usr/local/bin/ipxe-station* /etc/ipxe-station-report.conf 2>&1
    cat /etc/ipxe-station-report.conf 2>&1

    echo "== live-config log (last lines)"
    tail -n 40 /var/log/live/config.log 2>&1

    echo "== mounts"
    grep -E ' / |medium' /proc/mounts | cut -c1-150

    echo "== tools"
    for t in curl wget sudo dmesg journalctl lspci lsusb lsblk; do
        printf '%s: ' "$t"; command -v "$t" || echo missing
    done

    echo "== can it reach the server"
    curl -sS -m 10 -o /dev/null -w 'http=%{http_code}\n' "$SERVER_URL/ipxe/boot-report-debug" -X POST --data-binary ping 2>&1

    echo "== running the report job now, with tracing"
    if [ -x /usr/local/bin/ipxe-station-boot-report ]; then
        IPXE_STATION_REPORT_DELAY=0 sh -x /usr/local/bin/ipxe-station-boot-report 2>&1 | tail -n 40
        echo "job exit: $?"
    else
        echo "the job is not installed"
    fi
} > "$out" 2>&1

cat "$out"
curl -sS -m 20 -o /dev/null --data-binary "@$out" "$SERVER_URL/ipxe/boot-report-debug" 2>/dev/null && echo "--- sent to the server"
rm -f "$out"

#!/bin/sh
# Looks at why a boot report did not arrive, and sends what it finds to the iPXE Station server.
# Changes nothing except that it runs the report job once, right now.
SERVER_URL="__SERVER_URL__"
out="$(mktemp)"

# post <file> <url>: send a file with whatever the machine has (Ubuntu Desktop has only python3);
# prints http=<status> when it can tell.
post() {
    if command -v curl >/dev/null 2>&1; then
        curl -sS -m 20 -o /dev/null -w 'http=%{http_code}\n' --data-binary "@$1" "$2" 2>&1
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O /dev/null --post-file="$1" "$2" 2>&1 && echo "http=ok"
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c 'import sys, urllib.request as u; r = u.urlopen(u.Request(sys.argv[2], data=open(sys.argv[1], "rb").read(), method="POST"), timeout=20); print("http=%s" % r.status)' "$1" "$2" 2>&1
    else
        echo "no curl, wget or python3 to send with"
    fi
}

{
    echo "== kernel command line"
    tr ' ' '\n' < /proc/cmdline | grep -E 'hooks|BOOTIF|netboot|nfsroot|boot=|ipxe\.|layerfs'

    echo "== report layer on the medium (Ubuntu)"
    ls -la /run/live/medium/casper/zz-ipxe-station.squashfs /cdrom/casper/zz-ipxe-station.squashfs 2>&1
    grep -E 'zz-ipxe' /proc/mounts 2>&1 | cut -c1-150

    echo "== the report service (Ubuntu)"
    systemctl status ipxe-station-report.service --no-pager 2>&1 | head -12
    journalctl -u ipxe-station-report.service --no-pager 2>&1 | tail -8

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
    for t in curl wget python3 sudo dmesg journalctl lspci lsusb lsblk; do
        printf '%s: ' "$t"; command -v "$t" || echo missing
    done

    echo "== can it reach the server"
    ping_file="$(mktemp)"; echo ping > "$ping_file"
    post "$ping_file" "$SERVER_URL/ipxe/boot-report-debug"
    rm -f "$ping_file"

    echo "== running the report job now, with tracing"
    if [ -x /usr/local/bin/ipxe-station-boot-report ]; then
        IPXE_STATION_REPORT_DELAY=0 sh -x /usr/local/bin/ipxe-station-boot-report 2>&1 | tail -n 40
        echo "job exit: $?"
    else
        echo "the job is not installed"
    fi
} > "$out" 2>&1

cat "$out"
post "$out" "$SERVER_URL/ipxe/boot-report-debug" > /dev/null 2>&1 && echo "--- sent to the server"
rm -f "$out"

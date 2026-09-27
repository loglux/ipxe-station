#!/bin/sh
# Collects a boot report and sends it to the iPXE Station server that started this system.
# The address comes from /etc/ipxe-station-report.conf (written by a live-config hook) or from the
# kernel command line (ipxe.report=<url>, and ipxe.mac=<mac> to name the machine).
conf="${IPXE_STATION_CONF:-/etc/ipxe-station-report.conf}"
[ -r "$conf" ] && . "$conf"
PROC="${IPXE_STATION_PROC:-/proc}"
cmdline_value() { tr ' ' '\n' < "$PROC/cmdline" | sed -n "s/^$1=//p" | head -n 1; }
[ -n "$REPORT_URL" ] || REPORT_URL="$(cmdline_value ipxe.report)"
[ -n "$REPORT_URL" ] || exit 0
sleep "${IPXE_STATION_REPORT_DELAY:-${DELAY:-45}}"

out="$(mktemp)" || exit 0
section() { printf '##### %s\n' "$1"; }
text() { cut -c1-300; }

{
    section system
    if [ -r /etc/os-release ]; then . /etc/os-release; fi
    echo "os=${PRETTY_NAME:-unknown}"
    echo "kernel=$(uname -r)"
    echo "arch=$(uname -m)"
    if [ -d /sys/firmware/efi ]; then echo "boot=uefi"; else echo "boot=bios"; fi
    echo "uptime_s=$(cut -d. -f1 /proc/uptime)"

    section memory
    grep -E '^(MemTotal|SwapTotal):' /proc/meminfo

    section cpu
    grep -m1 'model name' /proc/cpuinfo | text
    echo "threads=$(grep -c '^processor' /proc/cpuinfo)"

    section dmi
    for f in sys_vendor product_name product_version bios_version bios_date chassis_type; do
        echo "$f=$(cat "/sys/class/dmi/id/$f" 2>/dev/null)"
    done

    section disks
    lsblk -dno NAME,SIZE,TYPE,TRAN,MODEL -e 7,11 2>/dev/null | text

    section pci
    lspci -nnk 2>/dev/null | text

    section usb
    lsusb 2>/dev/null | text

    section network
    ip -br link 2>/dev/null | text
    rfkill list 2>/dev/null | text

    section display
    for c in /sys/class/drm/card*-*; do
        [ -d "$c" ] || continue
        echo "$(basename "$c") $(cat "$c/status" 2>/dev/null) $(head -n 1 "$c/modes" 2>/dev/null)"
    done
    if command -v xrandr >/dev/null 2>&1; then
        xrandr --query 2>/dev/null | grep -E ' connected|\*' | text
    fi

    section power
    for p in /sys/class/power_supply/*; do
        [ -d "$p" ] || continue
        line="$(basename "$p")"
        for k in type status capacity cycle_count technology energy_full energy_full_design charge_full charge_full_design; do
            v="$(cat "$p/$k" 2>/dev/null)" && line="$line $k=$v"
        done
        echo "$line"
    done

    section kernel-messages
    { dmesg 2>/dev/null || sudo -n dmesg 2>/dev/null; } |
        grep -iE 'firmware: failed to load|Direct firmware load for|Failed to load (Intel )?firmware|\berror\b|\bfail(ed|ure)?\b|call trace|BUG:|timed out|I/O error|segfault|\boops\b|unable to|tainted' |
        text | head -n 300

    section failed-units
    systemctl --failed --no-legend --plain 2>/dev/null | text

    section journal-errors
    { journalctl -p err -b --no-pager -q 2>/dev/null || sudo -n journalctl -p err -b --no-pager -q 2>/dev/null; } |
        text | tail -n 80
} > "$out" 2>/dev/null

# Name the machine when the address does not already: the MAC of the card it network-booted from
# (ipxe.mac, or BOOTIF, on the kernel command line; else the card with the default route) and its
# model from DMI.
enc() { printf '%s' "$1" | sed 's/ /%20/g; s/[^A-Za-z0-9._%:-]//g'; }
url="$REPORT_URL"
case "$url" in
    *\?*) ;;
    *)
        mac="$(cmdline_value ipxe.mac)"
        [ -n "$mac" ] || mac="$(cmdline_value BOOTIF | sed 's/^01-//' | tr '-' ':')"
        if [ -z "$mac" ]; then
            dev="$(ip route show default 2>/dev/null | sed -n 's/.* dev \([^ ]*\).*/\1/p' | head -n 1)"
            [ -n "$dev" ] && mac="$(cat "/sys/class/net/$dev/address" 2>/dev/null)"
        fi
        vendor="$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null)"
        model="$(cat /sys/class/dmi/id/product_name 2>/dev/null)"
        url="$url?mac=$(enc "$mac")&manufacturer=$(enc "$vendor")&product=$(enc "$model")"
        ;;
esac

# Send it with whatever the image has: Debian's live image has curl and no wget; Ubuntu Desktop's
# has neither, but has python3.
if command -v curl >/dev/null 2>&1; then
    curl -fsS -m 30 -o /dev/null --data-binary "@$out" "$url" 2>/dev/null
elif command -v wget >/dev/null 2>&1; then
    wget -q -O /dev/null --post-file="$out" "$url"
elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import sys, urllib.request as u; u.urlopen(u.Request(sys.argv[2], data=open(sys.argv[1], "rb").read(), method="POST"), timeout=30)' "$out" "$url" 2>/dev/null
fi
rm -f "$out"

#!/bin/sh
# Boot report for a live system, made by iPXE Station for the machine that asked.
# Runs as a live-config hook early in boot, as root. It only sets up a small job; the job runs once
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
#!/bin/sh
# Collects a boot report and sends it to the iPXE Station server that started this system.
. "${IPXE_STATION_CONF:-/etc/ipxe-station-report.conf}" 2>/dev/null || exit 0
[ -n "$REPORT_URL" ] || exit 0
sleep "${IPXE_STATION_REPORT_DELAY:-$DELAY}"

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

wget -q -O /dev/null --post-file="$out" "$REPORT_URL"
rm -f "$out"
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

#!/bin/sh
# Text size for Kaspersky Rescue Disk, made by iPXE Station for the machine that asked.
# Runs as a live-config hook early in boot, before the desktop starts, and never fails the boot.
#
# SCALE is decided on the server: "off" (leave things alone), "auto" (work it out from the
# screen), or a number such as 1.5.

SCALE="__SCALE__"
REPORT_URL="__REPORT_URL__"   # where to tell the server about missing firmware; empty = do not

SYS="${IPXE_STATION_SYS:-/sys}"
PROC="${IPXE_STATION_PROC:-/proc}"
ROOT="${IPXE_STATION_ROOT:-}"
LOG="${ROOT}/var/log/ipxe-station-display.log"

mkdir -p "${ROOT}/var/log" 2>/dev/null
log() { echo "$*" >> "$LOG" 2>/dev/null; }

# Round a percentage to the nearest 25 (150, 175, ...), never below 100 or above 300.
round_pct() {
    r=$(( ($1 + 12) / 25 * 25 ))
    [ "$r" -lt 100 ] && r=100
    [ "$r" -gt 300 ] && r=300
    echo "$r"
}

# Percentage that makes text about as large as on a 96 dpi screen: width in pixels, width in mm.
pct_from_size() {
    [ "$1" -gt 0 ] && [ "$2" -gt 0 ] || return 1
    dpi=$(( $1 * 254 / ($2 * 10) ))
    pct=$(( dpi * 100 / 96 ))
    # Cinnamon doubles everything by itself on very dense screens; only the rest is ours.
    [ "$1" -ge 2880 ] && pct=$(( pct / 2 ))
    round_pct "$pct"
}

# Width of the panel in mm from its EDID, and its width in pixels from the preferred mode.
panel_scale() {
    for want in eDP LVDS DSI ""; do
        for dir in "$SYS"/class/drm/card*-*"${want}"*; do
            [ -d "$dir" ] || continue
            [ "$(cat "$dir/status" 2>/dev/null)" = "connected" ] || continue
            [ -r "$dir/edid" ] && [ -r "$dir/modes" ] || continue
            set -- $(od -An -tu1 -j66 -N3 "$dir/edid" 2>/dev/null)
            [ -n "$3" ] || continue
            width_mm=$(( $1 + $3 / 16 * 256 ))
            if [ "$width_mm" -le 0 ]; then
                set -- $(od -An -tu1 -j21 -N1 "$dir/edid" 2>/dev/null)
                width_mm=$(( ${1:-0} * 10 ))
            fi
            mode=$(head -n 1 "$dir/modes" 2>/dev/null)
            xres=${mode%%x*}
            case "$xres" in ''|*[!0-9]*) continue ;; esac
            found=$(pct_from_size "$xres" "$width_mm") || continue
            log "screen: ${dir##*/} ${mode}, ${width_mm} mm wide (from EDID)"
            echo "$found"
            return 0
        done
    done
    return 1
}

# Without a kernel video driver (nomodeset) there is no EDID: use the framebuffer size and,
# for laptops only, an assumed panel width of 340 mm (a 15.6 inch screen).
guess_scale() {
    size=$(cat "$SYS/class/graphics/fb0/virtual_size" 2>/dev/null)
    xres=${size%%,*}
    case "$xres" in ''|*[!0-9]*) return 1 ;; esac
    case "$(cat "$SYS/class/dmi/id/chassis_type" 2>/dev/null)" in
        8|9|10|14) ;;
        *) log "screen: ${size}, not a laptop, no size guess"; return 1 ;;
    esac
    found=$(pct_from_size "$xres" 340) || return 1
    log "screen: framebuffer ${size}, laptop, panel width assumed 340 mm"
    echo "$found"
}

# After the desktop is up, send the server the lines where the kernel could not find firmware, so it
# can recommend what to add to the disk, and what this script decided about the screen. Only those
# lines are sent.
setup_report() {
    [ -n "$REPORT_URL" ] || return 0
    bin="${ROOT}/usr/local/bin/ipxe-station-report"
    mkdir -p "${ROOT}/usr/local/bin" "${ROOT}/etc/xdg/autostart" 2>/dev/null
    cat > "$bin" <<EOS
#!/bin/sh
sleep "\${IPXE_STATION_REPORT_DELAY:-40}"
out=/tmp/ipxe-station-firmware.txt
{
    { dmesg 2>/dev/null || sudo -n dmesg 2>/dev/null; } | grep -iE 'firmware: failed to load|Direct firmware load for|Failed to load (Intel )?firmware'
    sed 's/^/ipxe-station-display: /' "$LOG" 2>/dev/null
} > "\$out"
wget -q -O /dev/null --post-file="\$out" '$REPORT_URL'
EOS
    chmod 755 "$bin"
    cat > "${ROOT}/etc/xdg/autostart/ipxe-station-report.desktop" <<EOD
[Desktop Entry]
Type=Application
Name=iPXE Station report
Exec=/usr/local/bin/ipxe-station-report
NoDisplay=true
EOD
    log "report: will send missing-firmware lines to the server"
}
setup_report

log "text size requested: $SCALE"
if grep -qw nomodeset "$PROC/cmdline" 2>/dev/null; then
    log "video: safe mode (nomodeset), the kernel video driver is off"
else
    log "video: the kernel video driver is on"
fi

case "$SCALE" in
    off)
        log "text size: left alone (set to off on the server)"
        exit 0
        ;;
    auto)
        pct=$(panel_scale) || pct=$(guess_scale) || {
            log "text size: could not work it out, left alone"
            exit 0
        }
        ;;
    *)
        # a number like 1.5 or 2.25, as hundredths
        whole=${SCALE%%.*}
        frac=${SCALE#*.}
        [ "$frac" = "$SCALE" ] && frac=0
        frac=$(printf '%s00' "$frac" | cut -c1-2)
        case "$whole$frac" in ''|*[!0-9]*)
            log "text size: '$SCALE' is not a number, left alone"
            exit 0
            ;;
        esac
        pct=$(( whole * 100 + ${frac#0} ))
        ;;
esac

if [ "$pct" -le 100 ]; then
    log "text size: 100%, nothing to change"
    exit 0
fi

factor="$(( pct / 100 )).$(printf '%02d' $(( pct % 100 )))"
dpi=$(( 96 * pct / 100 ))

schemas="${ROOT}/usr/share/glib-2.0/schemas"
if [ -d "$schemas" ]; then
    cat > "$schemas/99_ipxe-station.gschema.override" <<EOF
[org.cinnamon.desktop.interface]
text-scaling-factor=$factor
EOF
    if [ -z "$ROOT" ] && command -v glib-compile-schemas >/dev/null 2>&1; then
        glib-compile-schemas "$schemas" >> "$LOG" 2>&1 || log "glib-compile-schemas failed"
    fi
fi

# Programs that do not read Cinnamon's setting (Qt) take their font size from Xft.dpi.
mkdir -p "${ROOT}/etc/X11/Xresources" 2>/dev/null
echo "Xft.dpi: $dpi" > "${ROOT}/etc/X11/Xresources/99-ipxe-station"

log "text size: ${pct}% (text-scaling-factor $factor, Xft.dpi $dpi)"
exit 0

# iPXE Station — Roadmap

## Current State (2026-03-03)

### Execution Principles

- **Feature-first:** prioritize core PXE/iPXE functionality before non-critical hardening.
- **Backend as source of truth:** schema, recipes, and generation logic must stay in backend APIs.
- **Thin frontend:** UI renders and calls APIs; it must not become a second business-logic backend.
- **Security-by-boundary:** future auth should be added at API boundary (middleware/dependencies), not spread across domain logic.
- **Stable contracts:** keep API request/response models backward-compatible to allow incremental security rollout.
- **Optional hardening:** security controls should be modular and config-driven, with dev-friendly defaults.

### What Works

- **Proxy DHCP** — dnsmasq in proxy mode, correctly serves BIOS (`undionly.kpxe`) and EFI (`ipxe.efi`); auto-starts on container restart
- **PXE Boot on real hardware** — BIOS laptop confirmed working end-to-end
- **HTTP file serving** — `/srv/http/` at `/http/`, `/srv/ipxe/` at `/ipxe/` (no-cache), `/srv/tftp/` at `/tftp/`
- **Menu builder** — React SPA, scenario-based wizard, property panel, tree with inline controls
- **Boot Recipe Engine** — auto-generates correct `cmdline` per distro/version/boot-mode (Ubuntu Server NFS/ISO, Ubuntu Desktop NFS/ISO, Kaspersky KRD 18/24, SystemRescue, Debian)
- **Debian v1 modes** — `debian_netboot` and `debian_preseed` are first-class backend recipe scenarios
- **Debian Live prototype** — experimental backend/UI path exposed for research, not yet production-supported
- **DHCP Diagnostic** — scenario detection (`proxy_ok`, `conflict`, `no_pxe`, `wrong_server`, …) + actionable recommendations with Fix buttons
- **Asset manager** — download, upload, ISO extract; dynamic version pickers for Ubuntu Server, Ubuntu Desktop, SystemRescue, Kaspersky
- **NFS boot** — Ubuntu Server NFS option with auto-detected export path
- **Monitoring** — boot events, syslog, service status
- **Boot Files tab** — autoexec.ipxe editor plus managed Debian preseed profiles
- **Dark mode**, URL-hash tab persistence

---

### Known Bugs / Limitations

#### Medium

- **DHCP validator captures only first response** — on networks with both router DHCP and proxy DHCP,
  the validator may see the router first and miss the proxy response.
  Fix: collect all responses within a timeout window instead of returning on first packet.

- **autoexec.ipxe write via bash heredoc corrupts `#!ipxe`** — bash history expansion turns `!` into `\!`.
  Always write autoexec.ipxe via the Boot Files tab API or `docker cp` a pre-written file.

- **VirtualBox BIOS PXE doesn't work with iPXE UNDI** — VirtualBox's UNDI implementation fails for
  unicast TFTP/HTTP from within iPXE's own network stack. Works fine on real hardware.

#### Minor

- **DHCP validator iPXE probe shows `not_configured`** — validator expects HTTP URL in DHCP offer,
  but proxy DHCP gives a TFTP filename which then chains to HTTP. This is a false alarm; actual boot works.

- **autoexec.ipxe hardcodes server IP** — if server IP changes, autoexec must be updated manually.
  Fix: Boot Files tab should substitute `server_ip` from Settings at save time.

---

## Planned Features

### 1. DHCP Validator Multi-Response Collection

**Goal:** Detect proxy DHCP correctly even when a router also responds on the same network.

**Fix:** Collect ALL DHCP responses within a timeout window (e.g. 2 s) instead of returning on
the first packet. If two responses share the same XID — one from router (offered_ip ≠ 0), one
from proxy (offered_ip = 0.0.0.0) — classify accordingly.

### 2. PXELINUX Support

**Goal:** Alternative boot loader for environments where iPXE has issues (e.g. old hardware, VMs).

- Generate `pxelinux.cfg/default` from the same entry model (kernel/initrd/cmdline maps directly)
- Serve `pxelinux.0`, `menu.c32`, `ldlinux.c32` via TFTP
- "Dual export" button: generate both `boot.ipxe` and `pxelinux.cfg/default` from the same menu

### 3. Boot Files Tab: autoexec.ipxe Template Variables

**Goal:** autoexec.ipxe uses `server_ip` from Settings instead of a hardcoded address.

- Boot Files tab substitutes `${server_ip}` when saving/applying a template
- Fallback chain in autoexec: `${proxydhcp/siaddr}` → `${next-server}` → settings IP

### 4. Preseed / Cloud-init Editor

**Goal:** Generate Ubuntu preseed or cloud-init `user-data` / `meta-data` files from a form UI,
served over HTTP for automated installs.

### 5. Debian Live Validation

**Goal:** Turn the current Debian Live prototype into a documented, validated mode or remove it.

- Confirm which iPXE + Debian Live asset combinations are actually reliable on real hardware
- Document required files and working cmdlines
- Keep the scenario marked experimental until generator tests and boot verification agree
- Current documentation findings:
  - Debian separates installer media from Live install images
  - Live images are amd64-only and use Calamares
  - Debian live-boot expects `boot=live` and supports `fetch=` / `httpfs=` / `netboot=`
  - `fetch=` prefers IP-based URLs and can use a live ISO in place of squashfs

### 6. Optional LAN Security Hardening (No Overengineering)

**Goal:** Keep development friction low while reducing the highest-impact risks for LAN deployments.

- **Authentication remains optional** and disabled by default (`SECURITY_MODE=off`).
- Add lightweight optional token mode (`SECURITY_MODE=token`) for write/control API endpoints.
- Add configurable upload/download size limits to reduce accidental disk/IO exhaustion.
- Add optional SSRF guardrails for URL-based endpoints (`/api/assets/download`, `/api/assets/check-url`)
  with deny rules for loopback/private/metadata targets.
- Document trusted-LAN deployment assumptions and recommended network isolation
  (VLAN/firewall) as guidance, not as a mandatory runtime dependency.

---

## Boot File Architecture (Reference)

```
TFTP root: /srv/tftp/          → served at /tftp/ (HTTP) and port 69 (TFTP)
HTTP root: /srv/http/          → served at /http/
iPXE scripts: /srv/ipxe/       → served at /ipxe/ (no-cache headers)

Boot flow (BIOS):
  PXE ROM → TFTP undionly.kpxe
           → TFTP autoexec.ipxe
           → HTTP /ipxe/boot.ipxe   ← generated by menu builder
           → menu displays

Boot flow (EFI):
  UEFI PXE → TFTP ipxe.efi
            → TFTP autoexec.ipxe   ← must contain #!ipxe (not #\!ipxe)
            → HTTP /ipxe/boot.ipxe
            → menu displays

Key URLs:
  http://SERVER:9021/ipxe/boot.ipxe      ← generated iPXE menu (use this in autoexec)
  http://SERVER:9021/tftp/autoexec.ipxe  ← bootstrap script
  http://SERVER:9021/http/ubuntu-22.04/  ← distro assets
```

## Building Custom iPXE Binaries

The standard `undionly.kpxe` and `ipxe.efi` shipped in `data/srv/tftp/` are official upstream
builds and work for most setups. A custom build is only needed when you want to embed a startup
script or change compile-time options (e.g. enable HTTPS, change console output).

### Build environment (Linux / Docker)

```bash
# Clone iPXE source
git clone https://github.com/ipxe/ipxe.git
cd ipxe/src

# Optional: create an embedded script so iPXE auto-chains on boot
cat > embed.ipxe << 'EOF'
#!ipxe
dhcp
chain http://${next-server}:9021/ipxe/boot.ipxe || shell
EOF

# Build BIOS loader with embedded script
make bin/undionly.kpxe EMBED=embed.ipxe

# Build UEFI loader with embedded script
make bin-x86_64-efi/ipxe.efi EMBED=embed.ipxe

# Without embedded script (plain loader — chainloads via DHCP next-server)
make bin/undionly.kpxe
make bin-x86_64-efi/ipxe.efi
```

### Copy to project

```bash
cp bin/undionly.kpxe /path/to/ipxe-station/data/srv/tftp/undionly.kpxe
cp bin-x86_64-efi/ipxe.efi /path/to/ipxe-station/data/srv/tftp/ipxe.efi
```

### Notes
- Custom builds live in `*-custom.kpxe` locally and are excluded from git (`.gitignore`)
- The embedded script approach is optional: without it, the DHCP server must supply
  `next-server` + `filename` (or use Proxy DHCP with `pxe-service`) to point iPXE to
  `autoexec.ipxe` on TFTP
- HTTPS support requires additional compile flags: `TRUST=...` and a CA bundle

---

## Key Technical Findings

### Proxy DHCP
- Use `pxe-service` directive (NOT `dhcp-boot`) — only pxe-service sends both OFFER and ACK in proxy mode
- Do NOT use `dhcp-no-override` — it prevents dnsmasq from populating siaddr/BOOTP fields
- Option 43 sub-option **8** = Boot Servers (contains server IP). Sub-option 9 = Boot Menu label (NOT IP)
- iPXE BIOS sends DHCPREQUEST unicast to router → proxy never sees it → proxy must use pxe-service
  which uses PXE Boot Server protocol (separate from regular DHCP)

### File Serving
- `/srv/ipxe/boot.ipxe` — API-generated menu (correct, use this)
- `/srv/tftp/boot.ipxe` — chain-to-HTTP stub, updated by save_menu API
- autoexec.ipxe must chain to `/ipxe/boot.ipxe`, NOT `/tftp/boot.ipxe`

### Ubuntu Boot Modes
- **NFS** (`netboot=nfs nfsroot=`): reads squashfs on demand, no RAM limit — recommended for Server
- **HTTP ISO** (`url=`): downloads full ISO to RAM disk; Server needs ≥ 4 GB RAM, Desktop ≥ 8 GB
- **squashfs via `fetch=`**: broken on Ubuntu 22.04+ via iPXE ("no medium found") — do NOT use
- `root=/dev/nfs` is for traditional kernel NFS root, NOT for casper live boot — do not add it to casper cmdlines

## Recent Delivery Notes

### Smart Deploy Strategy
- Prefer the lightest deploy path:
  - `./deploy.sh frontend` for frontend-only changes
  - `./deploy.sh restart` for Python backend changes without image dependency changes
  - `./deploy.sh redeploy` for Dockerfile / requirements / runtime stack changes
- Fixed `deploy.sh` fallback path for hosts without `npm`: Docker-based frontend builds now mount the
  whole project (`$(pwd):/workspace`) so `app/frontend/dist` is updated on host reliably.

### Builder UX Direction
- `Menu Structure` received usability improvements:
  - full-row click selection
  - search + expand/collapse controls
  - reduction of inline control overlap issues
- Implemented navigation-first layout:
  - tree rows are focused on selection/navigation only
  - reordering/move/delete actions live in selected-entry panel below
- Added UI polish for half-width layouts:
  - larger row hit-area and control spacing
  - improved action panel readability and mobile wrapping behavior
- Visual consistency pass (Menu Structure):
  - stronger contrast for row states (`default/hover/focus/selected`)
  - clearer subtree hierarchy via subtle guide line
  - improved control readability in action panel

### Cross-Page UI Consistency Pass
- Aligned visual tone for `Monitoring`, `Assets`, `DHCP`, and `Boot Files`:
  - consistent card borders/contrast and typography scale
  - cleaner interactive states for filters/buttons/selects
  - improved readability at half-width desktop layouts
- Scope intentionally limited to presentation styles; no API or behavior changes.
- Follow-up polish:
  - removed remaining inline spacing styles in `Boot Files` in favor of CSS classes
  - normalized `Monitoring` control-button height/weight for cleaner toolbar rhythm

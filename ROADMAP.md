# iPXE Station — Roadmap

## Current State (2026-09-19)

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
- **UEFI-PXE on real hardware** — a Dell laptop (Secure Boot off, UEFI network stack on) booted
  UEFI PXE → iPXE menu → `wimboot` → a custom WinPE 26100 image; confirmed 2026-09-19 from the
  server's request log (`boot.ipxe`, `wimboot`, `BCD`, `boot.sdi`, `boot.wim`). Secure Boot on, HTTP
  Boot and other laptop models are still unverified.
- **Kaspersky Rescue Disk 24 over NFS** — on a Dell Latitude 5530 the live system now gets an address and
  mounts the NFS export (confirmed 2026-09-25 from server logs: DHCP request from the initramfs and an NFS
  mount request). It failed before the `BOOTIF` fix, see Key Technical Findings.
- **Kaspersky Rescue Disk upkeep** — from the Assets tab: update the antivirus databases (replace
  `live/KRD/30-bases.srm`, the module KRD's own updater replaces; verified with Kaspersky's SHA-512; backup
  kept; the disk's timestamp and `sha256sum.txt` updated) and build a small firmware archive
  (`linux-firmware-custom.tar.gz`) for chosen devices or for what a machine's `dmesg` reports. The manual
  database swap was confirmed on hardware ("Databases are up to date"), and so was the small firmware
  archive (Dell Latitude 5530: no more "hardware does not work correctly" warning). The firmware is now chosen from
  a catalog built from the official release's `WHENCE` (594 devices; big drivers such as iwlwifi split by chip),
  as none, selected devices or everything; machines can report missing firmware on their own through the boot
  script, which the page turns into recommendations. The databases can be checked (or updated) on a schedule set from the admin page; the update waits if a machine
  started Kaspersky recently. Planned: telling a running machine's NFS session from an idle one exactly, instead
  of going by when a machine last asked for the kernel.
  Screen text size and video mode are settable from the server; confirmed on the Dell Latitude 5530 with a
  fixed 150% and the native resolution (text is larger). "Automatic" was confirmed on the same laptop: the machine reported that it read the
  panel's size from its EDID (1920x1080, 344 mm wide) and chose 150%, the same as the fixed setting, and the text
  is larger than before. Not yet tried: rules per model.
- **Boot reports from live systems** — the report-and-recommend idea of the Kaspersky work, generalised: a
  `live-config` system (Debian Live) can be asked, per menu entry, to send a summary after it starts (memory, disks,
  PCI/USB with drivers, battery health, kernel errors, missing firmware, failed services), kept per machine and
  system on the Devices tab. Server side and script are tested and were run against the server; **not yet booted
  on a real Debian Live**. Ubuntu (`casper`, no `live-config`) needs another way to run a script; SystemRescue
  (`ar_source`) and WinPE (`start.ps1`) are candidates.
- **Rescuezilla and ShredOS** — download from the Assets tab (versions and checksums from the official GitHub
  releases, verified after download) and boot from the menu with recipes for NFS and ISO (Rescuezilla) and a
  single kernel image (ShredOS). Downloaded and in the menu; **not yet booted on real hardware**.
- **Windows PE via wimboot** — documented in the README (file layout, RAM, Secure Boot and
  RAID/VMD storage-driver notes)
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

- **autoexec.ipxe write via bash heredoc corrupts `#!ipxe`** — bash history expansion turns `!` into `\!`.
  Always write autoexec.ipxe via the Boot Files tab API or `docker cp` a pre-written file.

- **VirtualBox BIOS PXE doesn't work with iPXE UNDI** — VirtualBox's UNDI implementation fails for
  unicast TFTP/HTTP from within iPXE's own network stack. Works fine on real hardware.

- **WinPE sees no disks on RAID/VMD laptops** — with SATA operation set to "RAID On" (Intel
  RST/VMD) the NVMe disk is hidden until an `iaStorVD` storage driver is present. Add it to the WIM
  (`DISM /Add-Driver`) or `drvload` it at runtime; consider setting AHCI on machines being reprovisioned.

#### Minor

- **DHCP validator iPXE probe shows `not_configured`** — validator expects HTTP URL in DHCP offer,
  but proxy DHCP gives a TFTP filename which then chains to HTTP. This is a false alarm; actual boot works.

- **autoexec.ipxe hardcodes server IP** — if server IP changes, autoexec must be updated manually.
  Fix: Boot Files tab should substitute `server_ip` from Settings at save time.

---

## Planned Features

### 1. PXELINUX Support

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

### 6. Optional LAN Security Hardening (No Overengineering) — Delivered

**Goal:** Keep development friction low while reducing the highest-impact risks for LAN deployments.

- **Done** — `SECURITY_MODE=token` + `API_TOKEN` enforced at the single API boundary dependency
  (`app/routes/boundary.py`); authentication remains optional and disabled by default (`SECURITY_MODE=off`).
- **Done** — SSRF guardrails on `/api/assets/download` and `/api/assets/check-url`
  (`app/backend/url_guard.py`) deny loopback/private/link-local/reserved/multicast targets and
  re-validate redirect hops before following them.
- Configurable upload/download size limits — not yet done.
- Document trusted-LAN deployment assumptions and recommended network isolation
  (VLAN/firewall) as guidance — not yet done.

### 7. UEFI HTTP Boot (Experimental)

**Goal:** Give newer UEFI firmware a way to fetch `ipxe.efi` directly over HTTP(S), skipping the
TFTP hop entirely — additive only, the existing BIOS/UEFI-PXE-ROM path is unchanged.

- **Done** — opt-in `support_http_boot` toggle on the live Proxy DHCP dnsmasq instance
  (`app/backend/proxy_dhcp.py`): tags DHCP option 60 `HTTPClient` vendor-class requests separately
  from the existing `pxe-service` (BIOS/UEFI-PXE-ROM) branches, echoes the vendor-class back per
  RFC 5970, and responds with `dhcp-boot=http://SERVER:PORT/tftp/ipxe.efi`.
- **Done** — matching opt-in block in the dnsmasq router-config generator
  (`app/backend/dhcp_helper.py`) for users running their own external dnsmasq.
- **Not done** — no HTTP Boot support added to the isc-dhcp/mikrotik/windows generators (those
  platforms' mechanisms are less uniformly documented; follow the existing Windows-generator
  precedent of pointing to vendor docs rather than guessing).
- **Not done** — no synthetic `HTTPClient` probe added to `DHCPValidator`/network validation; the
  validator's raw-socket code has zero existing test coverage, and this would need real hardware to
  verify against rather than being added speculatively.
- Ecosystem context: IANA reserves architecture type `16` (`0x0010`) for x86-64 UEFI HTTPBoot in the
  PXE client-architecture registry (RFC 4578 successor allocations) — noted here for reference; the
  current implementation doesn't probe or branch on this code, it only reacts to the vendor-class string.

**Manual validation checklist** (unverified against real hardware in this environment — same
posture as the Debian Live prototype below):
1. Enable the "HTTP Boot (UEFI, experimental)" checkbox in the Proxy DHCP panel and start/restart it.
2. Boot a UEFI client whose firmware advertises native HTTP Boot support (check firmware boot-menu
   for an "HTTP Boot" or "Network Boot from URL" entry) and confirm it fetches `ipxe.efi` over HTTP
   rather than falling back to TFTP.
3. Confirm iPXE then finds and runs `autoexec.ipxe` via TFTP exactly as the regular UEFI path does.
4. Record whether `dhcp-option-force=60,"HTTPClient"` was actually necessary for the specific
   firmware tested, or whether it accepted the URL without the echo — capture findings here.

**UEFI-PXE validation checklist** (the `pxe-service=x86-64_EFI` path in `proxy_dhcp.py` exists but,
unlike BIOS PXE, has not been confirmed on real hardware — only BIOS is listed under "What Works"):
1. In firmware setup enable the UEFI network stack and turn Secure Boot off (note the original
   values first; if BitLocker is active, have the recovery key ready — changing Secure Boot state or
   boot order can trigger a recovery prompt).
2. One-time boot menu → onboard NIC (UEFI, IPv4). Confirm the "Network Boot (UEFI)" offer, that
   `ipxe.efi` loads over TFTP, and that `autoexec.ipxe` chains to `/ipxe/boot.ipxe`.
3. Boot live-only entries (SystemRescue, Hiren's PE, Debian Live) — never installers — and record
   per model: firmware version, boot time, RAM used, whether the NIC/USB-Ethernet adapter worked.
4. Repeat with each laptop model in the target fleet and record results in a per-model table here.

### 8. Secure Boot with an Organization Signing Key (Planned)

**Goal:** Let UEFI clients with Secure Boot enabled network-boot iPXE, by signing our own iPXE build
with an organization key and enrolling that certificate in the firmware — suitable for fleets under
one administrative domain (e.g. preparing many laptops), not for arbitrary machines.

- **Why it is needed:** the stock `ipxe.efi`/`snponly.efi` (local copies and the current
  `boot.ipxe.org` build, checked with `sbverify` on 2026-09-19) carry no Authenticode signature, so
  firmware with Secure Boot on refuses them. UEFI HTTP Boot does not avoid this — the firmware still
  verifies the `.efi` file. Let's Encrypt is unrelated: it issues TLS certificates, not code-signing
  trust that firmware honours.
- **Approach (not started):** build iPXE from source in Docker (the existing "Building Custom iPXE
  Binaries" section), sign with `sbsign` using the organization's Secure Boot key, and enroll the
  certificate into the firmware `db` while keeping the Microsoft entries. `wimboot` (v2.9.0, pinned
  in the Dockerfile) is already signed by Microsoft (UEFI CA 2011, checked with `sbverify` on
  2026-09-19), so only iPXE itself needs our signature for the WinPE path; other chained EFI
  binaries must be checked individually. The same custom build can embed the organization CA (`TRUST=`) so iPXE can
  use HTTPS to this server without a public certificate.
- **Constraints to design around:**
  - The private signing key must never live under `data/` — `/srv/tftp` and `/srv/http` are served
    over HTTP. Keep it offline or in a build-only volume.
  - Enrollment is per machine (firmware UI "custom/expert key management", or scripted from a Linux
    stage while the machine is in Setup Mode); firmware admin password policy applies.
  - Distro kernels are signed with distro keys chained through shim, not the firmware `db`, so Linux
    live entries need a shim chain or re-signed binaries. WinPE via `wimboot` is the expected
    workable path (`wimboot` and `bootmgr` are both Microsoft-signed) — to be confirmed on hardware.
- **Interim approach:** keep Secure Boot off during provisioning and enable it as the last
  provisioning step.
- **Validation:** boot a signed build with Secure Boot on for each target model; record which entry
  types (WinPE, SystemRescue, Debian/Ubuntu live) load and which are rejected.

### 9. Device Scenarios (Planned)

**Goal:** Let the server decide what a machine should do at network boot, from what it reports about
itself (brand, model, SKU, serial, BIOS version). Two ways to run a scenario: **offered** in the machine's
own PXE menu for the operator to choose, or **automatic** after a short cancellable countdown.

**Core mechanism:** the server builds the iPXE menu **per machine**. `boot.ipxe` stays a small static
stub: it reports the machine (already done), then chains to a server-built menu
(`/ipxe/menu?mac=&uuid=&manufacturer=&product=&sku=&bios_version=`) and falls back to the current static
menu if the server does not answer. A scenario describes: which machines it applies to, what it runs (an
existing menu entry, or a job for a WinPE/Linux executor), the mode (offer / auto with countdown), and how
often it may run.

**What a scenario can do (the target list):**
- **Install Windows with the right drivers** for the model: image (WIM) library, disk layout templates
  (UEFI/GPT), unattended answer files with variables (computer name from serial or asset tag, locale, local
  admin, domain or Entra join), per-model driver packs injected at install, post-install packages and a
  first-boot script.
- **Update BIOS** per model (package + SHA256, guards: AC power, battery, BitLocker, allow-list, attempt limit).
- **Change BIOS settings** per model from a profile (desired state; audit and diff first; Secure Boot last; BIOS
  password kept out of published files).
- **Also:** read-only hardware audit and post-provisioning verification (BIOS version, settings, drivers,
  encryption) shown as compliance in the Devices tab; ordered **workflows** (steps, conditions, reboots,
  retries) such as "update BIOS, apply settings, install Windows, verify"; device **groups and tags** (lab,
  staff, batch); asset tagging and naming; secure erase with a certificate; Linux installs; Autopilot/Intune
  registration; Wake-on-LAN maintenance windows; notifications; an **audit log** and per-serial **allow-lists**
  for anything that writes to a machine.

**Everything is set up in the web UI, and every setting is also data.** The wizard and the editors only
write the same human-readable files (JSON, in `data/srv/ipxe/`), so nothing has to be clicked through twice:
- **Profiles and packages:** BIOS settings profiles, BIOS packages per model, driver packs, OS images, answer
  file templates, disk layouts, workflows, scenarios, groups, allow-lists.
- **Export / import:** export one object or a whole bundle (zip: the config files plus a manifest; large
  binaries are referenced by name and SHA256 and optionally included; **secrets are never exported**). Import
  shows a preview with validation and a diff, then applies it; conflicts are chosen per object. Bundles can be
  kept in git and copied to another server.
- **Reuse instead of wizard-every-time:** clone an existing scenario or profile, start from ready presets
  (for example "Dell Latitude standard"), and **capture a profile from a golden machine** (read its BIOS
  settings, then save them as a profile).
- **API first:** the UI uses the same `/api/...` calls, so config can be scripted.

**Stages (each usable on its own):**
1. **Per-machine menu and device info — done, one real boot confirmed.** `boot.ipxe` asks `/ipxe/menu`, the
   server answers with the menu plus a "Recommended for this device" block and a *Device information* screen;
   rules live in `scenarios.json` (`GET`/`PUT /api/scenarios`), an automatic scenario is pre-selected with a
   countdown, and the Devices tab lists the scenarios that apply. Read-only, nothing is changed on the client.
   Confirmed on a Dell Latitude 5530 (the recommended block appears); still to confirm on real iPXE: the
   `chain ... && exit || goto start` fallback and the `prompt` on the information screen.
2. **Configuration as data.** One config store with validation, groups and tags for devices, the scenario
   editor in the UI (list, edit form, clone, enable/disable), and **export/import with preview**. Built before
   the features below so each of them stores its settings the same way.
3. **Jobs and workflows.** The chosen scenario is remembered per machine; a booted WinPE or Linux asks the
   server "what should I do?" (by MAC/UUID) and receives its steps. States (queued, running, done, failed),
   attempt limits, an audit log, allow-lists, and the wizard that builds a workflow.
4. **Hardware audit (read-only) and compliance.** SystemRescue's autorun (present in 12.03, with `dmidecode`,
   `smartctl`, `lscpu`, `lsblk`, `nvme`, `upower`, `ethtool`, `lspci`) or the WinPE `start.ps1` collects CPU,
   memory, disks and SMART, battery wear, NICs and, where the kernel exposes it, BIOS settings
   (`/sys/class/firmware-attributes`), and posts JSON to the server; shown in the Devices detail.
5. **BIOS.** Per-model target versions shown as compliance first, then the update job on one model (after a
   test on a machine that can be recovered); then settings profiles with diff, apply, and capture from a
   golden machine.
6. **Windows installation (first priority for provisioning).** Image and driver-pack library, answer-file
   templates with variables, disk layouts, first-boot configuration, post-install **packages** (name,
   installer file or URL, silent arguments, detection rule, groups) installed as a workflow step, a
   verification step; per-model driver selection.
7. **Later:** Linux installation, secure erase, asset tagging, Autopilot/Intune, Wake-on-LAN windows,
   notifications, central logging, and **software distribution to running machines**. Installing software
   during provisioning (stage 6) needs only what we have; keeping software up to date on machines that are
   already in use needs an agent or an existing tool (winget, Intune, SCCM) and is a separate decision.

**Tools catalog (can run in parallel with the stages):** a generic *Add tool from ISO* flow. The ISO is
uploaded or dropped into Assets, its layout is detected (`sources/boot.wim` → WinPE via wimboot; `live/` +
squashfs → live-boot; `casper/` → Ubuntu; archiso; syslinux or GRUB config → parsed for kernel/initrd and
parameters), and a menu entry is created with the right command line (including the boot-NIC parameter for
live-boot). Each tool is a preset in the same config format (files needed, boot method, command line, RAM,
BIOS/UEFI support, licence note, verified status), so presets can be exported and imported. **Started:**
Rescuezilla and ShredOS are the first entries of a server-side tool catalog (`tool_catalog.py`,
`GET /api/assets/tools`) with a generic download section in the UI; new tools are added to that list. Candidates:
AOMEI Backupper and PE Builder, Acronis True Image bootable media, Macrium Reflect rescue media, Veeam
recovery media, Bitdefender/ESET/Dr.Web rescue disks, Ultimate Boot CD, Windows installation media. Commercial tools use the bootable media their own product builds, under their own
licence. Backup images and large install sources need a network target: an SMB share or an HTTP download step.

**Safe first scenarios to try on real hardware:** device information; a recommended live system for a
model (Kaspersky or SystemRescue); BIOS compliance display (no flashing); read-only hardware audit.
Anything that writes to the machine (BIOS update, settings, install, erase) comes after these, behind an
allow-list and a confirmation.

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

### live-boot picks the wrong network card

Debian live-boot (Debian Live, Kaspersky Rescue Disk 24) uses the first interface that reports a link. On
a laptop with a cellular modem that is `wwan0` (wired `eth0` gets its link half a second later), and
`ipconfig` then fails with "no devices to configure", ending in `NFS over TCP not available from <server>`.
Fix: add `BOOTIF=01-${net0/mac:hexhyp}` to the command line (iPXE fills in the MAC of the boot NIC). The boot
recipes and the KRD scenario template include it, and Save Menu warns when a network live entry lacks
`BOOTIF=`/`ethdevice=`/`live-netdev=`. Diagnosis that worked: the client's DHCP requests and NFS mount
requests in the server log (none arrived), then the on-screen text.

### How Kaspersky Rescue Disk 24 keeps databases and firmware

- The disk is `live/KRD/{10-krd,20-krt,30-bases}.srm` on top of `filesystem.squashfs`. The antivirus
  databases are only `30-bases.srm`. Kaspersky publishes a newer one as
  `https://rescuedisk.s.kaspersky-labs.com/updatable/2024/bases/42-freshbases.srm`, with its SHA-512 in
  `hashes.txt` and the release timestamp in `krd.xml` (`databases_timestamp`). The disk remembers its own in
  `krd_bases_timestamp.txt`; `sha256sum.txt` is only read by KRD's `verify-checksums`.
- Replacing `30-bases.srm` is enough: KRD showed "Databases are up to date". A machine running KRD reads that
  file over NFS, so replace it while none is running.
- Firmware: the boot hook (`live/boot/9990-firmware`) unpacks exactly one `linux-firmware-*.tar.gz` from the
  disk root and runs `<name>/copy-firmware.sh` from it (two archives make it panic; under ~3.1 GB of RAM it
  skips them). A small archive with its own `copy-firmware.sh` therefore works as well as the full release.
- The kernel (6.1) asks for Wi-Fi firmware API 72; linux-firmware `20230210` still has it, newer releases may
  not. kernel.org answers 403 to the default python-requests User-Agent.
- The warning dialog comes from `krt.sh`, which greps `dmesg` for `firmware: failed to load`.
- Desktop: Cinnamon under lightdm. Cinnamon's `scaling-factor=0` only doubles on very dense screens, so a
  15 inch Full HD panel stays at 96 dpi. `live-config` runs before `basic.target`, i.e. before the desktop, and
  its `live-config.hooks=<url>` argument downloads and runs a script as root; iPXE Station serves one at
  `/ipxe/krd-display.sh`, made per machine (rules on brand/model, else a default; "auto" reads the panel's EDID
  size, or guesses for laptops when `nomodeset` leaves no EDID). It writes a gsettings override
  (`text-scaling-factor`) and `Xft.dpi`. `nomodeset`, which the NFS template carries, keeps the video driver out
  and leaves the resolution to the firmware.


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
- Added productivity controls in `Menu Structure`:
  - `Duplicate` selected entry with deterministic unique naming (`*_copy`, `*_copy2`, ...)
  - bulk toggles: `Enable all` / `Disable all`
  - scoped toggles for selected item and selected subtree
- Extended builder Playwright smoke to cover duplicate + bulk enable/disable flows.
- Started Builder phase-1 drag-and-drop:
  - drag entry onto a submenu to re-parent it
  - drag entry to root drop-zone to move it to root level
  - invalid moves (self/descendant) are blocked in UI logic
- Follow-up fix:
  - drag-and-drop now commits positional reorder (drop after target row), so moved items
    stay in the new place consistently.
- Precision UX update:
  - row drop now supports `before/after` insertion by cursor position (upper/lower half),
    improving accurate swaps and neighbor reordering.

### Cross-Page UI Consistency Pass
- Aligned visual tone for `Monitoring`, `Assets`, `DHCP`, and `Boot Files`:
  - consistent card borders/contrast and typography scale
  - cleaner interactive states for filters/buttons/selects
  - improved readability at half-width desktop layouts
- Scope intentionally limited to presentation styles; no API or behavior changes.
- Follow-up polish:
  - removed remaining inline spacing styles in `Boot Files` in favor of CSS classes
  - normalized `Monitoring` control-button height/weight for cleaner toolbar rhythm
- Wide-screen adaptation pass (layout-only):
  - removed per-page fixed max-width centering in main tabs
  - aligned `Builder/Assets/DHCP/Boot/Monitoring` to use the same full content width behavior
  - no business logic changes; CSS-only adaptation
- Assets visual cleanup (step-by-step):
  - removed remaining inline styles from `AssetManager.jsx`
  - introduced shared progress UI block/classes for Ubuntu/Debian/SystemRescue/Kaspersky
  - kept behavior unchanged (presentation-only refactor)
  - normalized subsection wrappers/headings across Ubuntu, Debian, and Tools download blocks
    to use one section rhythm and card template framing (layout-only)
- Navigation decision (accepted):
  - keep a single navigation axis in the app shell (no duplicated global + local sidebars
    with overlapping purpose on the same screen)
  - for current stage, keep global sidebar as primary and use in-page tabs/toolbar for local context

### Command Line Assistant (Phase 1, frontend-only)
- Added cmdline helper in `PropertyPanel` without backend/API changes:
  - generic overlay sets (not distro templates) for fine tuning
  - token suggestions with insert/replace-by-key behavior
  - user custom sets (`Save current as set`) persisted in browser localStorage
  - soft warnings for common cmdline issues
- Existing Ubuntu/Debian backend recipe/template flow remains unchanged.
- Replaced placeholder path tokens in helper flow:
  - generic sets keep only non-path overlays
  - exact path/value tokens (`nfsroot`, `url`, etc.) are sourced from backend boot recipe suggestions.
- Explicit follow-up after resource model:
  - remove temporary warning text example `nfsroot=SERVER:/path`
  - replace with concrete `nfsroot` from selected backend resource (`resource_id`) once
    Assets/Builder resource linkage is implemented.

### Archive Research Notes
- Added `docs/boot-variations-catalog.md`:
  - captures legacy-observed boot variation families as abstractions
  - explicitly avoids 1:1 legacy menu migration
  - defines compact initial `boot_method` set for future backend/UI phases
- Assets UI phase-1 inventory workspace:
  - replaced flat "All Files" list with `filters + list + details` layout
  - supports search and source/type/pack/status filters on `/srv/http` assets
  - keeps backend/API contracts unchanged (frontend-only adaptation)
- Acquire presets migration (phase-0 backend contract):
  - added backend preset catalog endpoint `GET/POST /api/assets/presets`
    backed by `system_presets.json` + `user_presets.json` in server data store
  - moved hardcoded `Ubuntu/Debian/Tools` navigation intent into system preset seeds
  - frontend `Assets` now reads acquire navigation from backend presets list
- IA hold decision:
  - `Library / Resource Inventory` is temporarily hidden from UI
  - keep Acquire flow clean while global sidebar role and full Assets IA are finalized
  - revisit library placement after shell-level navigation decision is fully implemented
- Antivirus presets note:
  - `Antivirus` preset group is enabled with Kaspersky flow separated from generic tools
  - ESET/NOD should be added as `manual-first` preset unless a stable official download source
    is available again

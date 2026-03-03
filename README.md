# iPXE Station

**iPXE Station** is a self-hosted PXE/iPXE boot server with a modern web interface. It handles the full workflow: downloading distro assets, building hierarchical boot menus, and configuring DHCP — all without touching config files manually.

## ✨ Features

### 🎨 Visual Menu Builder
- **Scenario-based wizard** — pick a distro/scenario, choose a downloaded version, and kernel/initrd/cmdline are auto-filled
- **Boot Recipe Engine** — automatically generates correct kernel parameters per distro and boot mode (NFS, HTTP ISO, netboot)
- **Hierarchical menus** — create submenus to organise entries
- **Tree editor** — inline move, delete, disable controls on hover
- **Live preview** — see the generated iPXE script in real time

### 📦 Asset Manager
- **Ubuntu Server & Desktop LTS** — dynamic version picker, downloads directly from releases.ubuntu.com
- **SystemRescue, Kaspersky Rescue Disk, Debian** — version pickers with direct ISO/netboot downloads
- **Automatic ISO extraction** — ISOs are extracted in-place for network boot
- **Real-time progress bars** — per-file progress (kernel, initrd, ISO) with GB counter
- **Upload & catalog scan** — upload any file, scan local assets

### 🌐 DHCP Configuration
- **Proxy DHCP server** — built-in dnsmasq in proxy mode (BIOS + EFI), starts automatically on container restart
- **Config generator** — ready-to-paste configs for dnsmasq, ISC DHCP, MikroTik RouterOS, Windows Server
- **Network validator** — sends real DHCP probes (BIOS, UEFI, iPXE) and diagnoses the result with fix suggestions

### 🔧 Boot Files
- **autoexec.ipxe editor** — edit or apply templates directly from the UI
- **NFS boot** — Ubuntu Server NFS cmdline with auto-detected export path

### 📊 Monitoring
- Live boot event log
- Syslog stream
- Service status (TFTP, HTTP, dnsmasq)

---

## 📋 Requirements

- **Docker** and Docker Compose
- **Disk space**: 5–10 GB typical (20+ GB with Desktop ISOs)
- **Ports**: 9021 (HTTP/UI), 69 (TFTP), 67 (DHCP — only if using Proxy DHCP)
- **Capability**: `NET_ADMIN` for DHCP validation and Proxy DHCP (already in `docker-compose.yml`)

---

## 🚀 Quick Start

```bash
git clone https://github.com/loglux/ipxe-station.git
cd ipxe-station
docker-compose up -d --build
```

Open **http://localhost:9021/ui**

### Download a distro

1. **Assets** tab → Quick Download
2. Select Ubuntu Server/Desktop or SystemRescue version
3. Click **Download ISO** — extraction happens automatically
4. ISO contents appear in the catalog when done

### Create a boot menu entry

1. **Builder** tab → click **+ Add Entry**
2. Pick category → scenario (e.g. *Ubuntu Live*)
3. Select downloaded version → boot mode auto-selected (NFS / HTTP ISO)
4. Click **Create** — kernel, initrd and cmdline are filled automatically
5. **💾 Save Menu**

### Configure DHCP

1. **DHCP** tab → select your server type
2. Copy the generated config to your DHCP server
3. Or use **Proxy DHCP** — enable it directly in the UI (no router changes needed)

---

## 🌐 Access Points

| Service | URL |
|---------|-----|
| Web UI | http://localhost:9021/ui |
| API docs | http://localhost:9021/docs |
| iPXE boot script | http://localhost:9021/ipxe/boot.ipxe |
| TFTP | tftp://localhost:69 |

---

## 🎯 Supported Scenarios

### 🐧 Linux
| Scenario | Description |
|----------|-------------|
| Ubuntu Server Live | Server ISO boot — NFS (recommended) or HTTP ISO |
| Ubuntu Desktop Live | Desktop ISO boot — NFS or HTTP ISO (≥ 8 GB RAM) |
| Ubuntu Preseed | Automated server install |
| Debian Netboot | Network installer (12 Bookworm, 13 Trixie) |

### 🛠️ Rescue & Tools
| Scenario | Description |
|----------|-------------|
| SystemRescue | Recovery environment, HTTP boot |
| Kaspersky Rescue Disk | KRD 18 (netboot) and KRD 24 (ISO fetch) |
| Memtest86+ | Memory testing |

### 🪟 Windows
| Scenario | Description |
|----------|-------------|
| Windows PE | WIMBoot preinstallation environment |

### 📂 Organisation
- **Submenu** — group related entries
- **Separator** — visual divider

### ⚙️ Actions
- Reboot, iPXE Shell, Exit to BIOS, Chain to another bootloader, Custom entry

---

## 📁 Directory Structure

```
./data/srv/
├── tftp/                    # TFTP boot files (port 69)
│   ├── undionly.kpxe        # BIOS iPXE loader
│   ├── ipxe.efi             # UEFI iPXE loader
│   └── autoexec.ipxe        # Bootstrap — chains to HTTP menu
├── http/                    # HTTP assets (/http/)
│   ├── ubuntu-22.04/        # Ubuntu 22.04 Server (extracted ISO)
│   ├── ubuntu-24.04-desktop/ # Ubuntu 24.04 Desktop (extracted ISO)
│   ├── rescue-12.03/        # SystemRescue
│   └── debian-12/           # Debian netboot files
├── ipxe/                    # iPXE scripts (/ipxe/, no-cache)
│   └── boot.ipxe            # Generated boot menu
└── dhcp/                    # Generated DHCP configs
```

---

## ⚙️ Configuration

### Environment Variables (`docker-compose.yml`)

```yaml
environment:
  - PXE_SERVER_IP=192.168.1.100   # Your server's IP address
  - HTTP_PORT=9021
  - TFTP_PORT=69
```

### NFS Boot (Ubuntu Server)

For NFS boot mode, configure the NFS export on your host:

```bash
sudo bash scripts/setup-nfs.sh
```

Then set the export path in **Settings → NFS Boot Root**.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────┐
│  React Frontend (Vite + React 18)            │
│  Menu Builder · Asset Manager · DHCP Helper  │
│  Boot Files · Monitoring · Settings          │
└──────────────────┬───────────────────────────┘
                   │ REST API
┌──────────────────┴───────────────────────────┐
│  FastAPI Backend                             │
│  iPXE generator · Boot Recipe Engine        │
│  Asset downloader/extractor · DHCP helper   │
│  Proxy DHCP (dnsmasq) · File serving        │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────┴───────────────────────────┐
│  Storage (Docker volumes)                    │
│  /srv/tftp  /srv/http  /srv/ipxe  /srv/dhcp  │
└──────────────────────────────────────────────┘
```

---

## 🧪 Development

```bash
python -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/pre-commit install

make format        # black + isort
make backend-lint  # ruff
make backend-test  # pytest (95 tests)
make quality       # all of the above
```

---

## 🔍 Troubleshooting

**PXE boot not working**
1. Check TFTP files: `ls data/srv/tftp/`
2. Verify autoexec.ipxe chains to `/ipxe/boot.ipxe` (not `/tftp/boot.ipxe`)
3. Test: `curl http://SERVER:9021/ipxe/boot.ipxe`
4. Check firewall: ports 69/UDP and 9021/TCP must be open

**DHCP validation fails**
- Container needs `NET_ADMIN` capability (already set in `docker-compose.yml`)
- Validation is optional — config generation works without it

**autoexec.ipxe gets corrupted**
- Never write it via bash heredoc (`!` gets escaped by bash history expansion)
- Use the Boot Files tab in the UI, or `docker cp` a pre-written file

**Ubuntu boots to console instead of desktop**
- Server ISO → always CLI (correct)
- For Desktop GUI: download Ubuntu Desktop ISO via Assets tab (separate from Server)

---

## 📝 License

MIT — see [LICENSE](LICENSE)

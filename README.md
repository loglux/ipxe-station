# iPXE Station

**iPXE Station** is a modern PXE/iPXE server with a powerful web interface for managing network boot infrastructure. Build complex boot menus, manage assets, and configure DHCP - all through an intuitive UI.

## ✨ Key Features

### 🎨 **Visual Menu Builder**
- **Scenario-based design** - Choose from pre-configured scenarios (Ubuntu, Debian, SystemRescue, Windows PE)
- **Drag & drop ordering** - Reorder entries with intuitive up/down buttons
- **Smart asset detection** - Automatically detects downloaded files and suggests versions
- **Hierarchical menus** - Create submenus to organize boot options
- **Live preview** - See generated iPXE script in real-time

### 📦 **Asset Manager**
- **Multi-distro support** - Ubuntu, Debian, Windows, SystemRescue
- **Parallel downloads** - Kernel + initrd download simultaneously
- **Progress tracking** - Real-time progress bars for each file (kernel, initrd, ISO)
- **Persistent across tabs** - Download progress survives tab switches
- **Automatic extraction** - ISO files automatically extracted for network boot
- **Version catalog** - Browse and download specific versions

### 🌐 **DHCP Configuration Helper**
- **Multi-platform support** - dnsmasq, ISC DHCP, MikroTik RouterOS, Windows Server
- **Auto-generation** - Generate ready-to-use DHCP configurations
- **Network validation** - Test DHCP setup (requires NET_ADMIN capability)
- **Copy-paste ready** - Configurations include architecture detection and iPXE chaining

### 🚀 **REST API**
- **Menu management** - Validate, generate, and save iPXE menus
- **Asset operations** - Download, upload, extract ISOs
- **DHCP tools** - Generate configs, validate network setup
- **System status** - Monitor server health and file counts

## 📋 Requirements

- **Docker** and Docker Compose
- **Disk space**: ~5-10GB for typical setup (more for ISOs)
- **Network**: Internet access for downloading distros
- **Ports**: 9021 (HTTP), 69 (TFTP)

## 🧪 Development Checks

Install backend dev tools:

```bash
python -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
```

Run quality checks:

```bash
make format
make backend-lint
make backend-test
make frontend-check
make quality
```

Install pre-commit hooks:

```bash
./.venv/bin/pre-commit install
```

## 🚀 Quick Start

### 1. Clone and Deploy

```bash
git clone https://github.com/loglux/ipxe-station.git
cd ipxe-station
docker-compose up -d --build
```

### 2. Access the UI

Open your browser: **http://localhost:9021/ui**

### 3. Download a Distribution

1. Go to **Assets** tab
2. Select a distro (e.g., Ubuntu 22.04 Netboot)
3. Click **Download**
4. Watch real-time progress bars

### 4. Create Boot Menu

1. Go to **Builder** tab
2. Click a category card (e.g., **Linux**)
3. Select scenario (e.g., **Ubuntu Netboot**)
4. Choose downloaded version from dropdown ✅
5. Click **Create Entry** - kernel/initrd auto-filled!

### 5. Save and Boot

1. Click **💾 Save Menu** in the header
2. Configure your DHCP server (see **DHCP** tab)
3. Boot a client via PXE!

## 🌐 Access Points

| Service | URL | Description |
|---------|-----|-------------|
| **Web UI** | http://localhost:9021/ui | Main interface |
| **API Docs** | http://localhost:9021/docs | Interactive API documentation |
| **Status** | http://localhost:9021/status | Server health check |
| **iPXE Boot** | http://localhost:9021/ipxe/boot.ipxe | Boot script endpoint |
| **TFTP** | tftp://localhost:69 | TFTP server |

## 🎯 Scenarios

iPXE Station uses a **scenario-first approach** - instead of technical iPXE details, you pick what you want to do:

### 🐧 Linux
- **Ubuntu Netboot** - Network installation (requires internet)
- **Ubuntu Live** - Boot from ISO (works offline)
- **Ubuntu Preseed** - Automated installation
- **Debian Netboot** - Network installation

### 🛠️ Rescue & Tools
- **SystemRescue** - Recovery and maintenance tools
- **Memtest86+** - Memory testing

### 🪟 Windows
- **Windows PE** - WIMBoot preinstallation environment

### 📂 Organization
- **Submenu** - Group related entries
- **Separator** - Visual divider

### ⚙️ Actions
- **Reboot** - Restart computer
- **iPXE Shell** - Drop to command line
- **Exit to BIOS** - Return to firmware

### 🔧 Advanced
- **Chain to Another Bootloader** - Transfer to PXELinux, GRUB, etc.
- **Custom Entry** - Full manual control

## 📁 Directory Structure

```
./data/srv/
├── tftp/              # TFTP boot files
│   ├── undionly.kpxe  # BIOS iPXE loader
│   ├── ipxe.efi       # Generic UEFI iPXE loader
│   └── snponly.efi    # UEFI iPXE via firmware SNP stack
├── http/              # HTTP boot files
│   ├── ubuntu-22.04/  # Ubuntu 22.04 files
│   │   ├── vmlinuz    # Kernel
│   │   ├── initrd     # Initial ramdisk
│   │   └── *.iso      # ISO file (optional)
│   ├── rescue-12.03/  # SystemRescue
│   └── debian-12/     # Debian
├── ipxe/              # iPXE scripts
│   └── boot.ipxe      # Generated boot menu
└── dhcp/              # DHCP configs
    ├── dnsmasq.conf
    ├── dhcpd.conf
    └── mikrotik-commands.txt
```

## 🔧 Configuration

### Environment Variables

Edit `docker-compose.yml`:

```yaml
environment:
  - PXE_SERVER_IP=192.168.10.32  # Your server IP
  - HTTP_PORT=9021                # HTTP port
  - TFTP_PORT=69                  # TFTP port
```

### DHCP Server Setup

1. Go to **DHCP** tab in UI
2. Select your DHCP server type
3. Enter server IP
4. Click **Generate Configuration**
5. Copy configuration to your DHCP server

**Example for dnsmasq:**
```bash
# Add to /etc/dnsmasq.conf
dhcp-match=set:ipxe,175
dhcp-boot=tag:ipxe,http://192.168.10.32:9021/ipxe/boot.ipxe
dhcp-boot=tag:!ipxe,undionly.kpxe,192.168.10.32
```

## 🎨 UI Features

### Builder Tab
- **Visual menu editor** with tree structure
- **Entry properties** - Edit name, title, kernel, initrd, cmdline
- **Order controls** - Move entries up/down with ▲/▼ buttons
- **Delete confirmation** - Safe removal of entries
- **Expert mode** - Toggle advanced fields

### Assets Tab
- **Download manager** with multiple distros
- **Progress indicators** for kernel, initrd, and ISO separately
- **Version selector** for Ubuntu and SystemRescue
- **File browser** - View all downloaded files
- **Catalog** - See what's available locally

### DHCP Tab
- **Server type selector** - dnsmasq, ISC DHCP, MikroTik, Windows
- **IP configuration** - Set server IP and ports
- **One-click generation** - Get ready-to-use configs
- **Network validation** - Test DHCP response (requires capabilities)

### Preview Tab
- **Live iPXE script** - See what will be generated
- **Syntax highlighting** - Readable script format
- **Warnings** - Validation messages
- **Refresh button** - Regenerate on demand

## 🚀 API Examples

### Create Entry via API

```bash
curl -X POST http://localhost:9021/api/ipxe/menu/save \
  -H "Content-Type: application/json" \
  -d '{
    "title": "PXE Boot Menu",
    "timeout": 30000,
    "entries": [
      {
        "name": "ubuntu_2204",
        "title": "Ubuntu 22.04",
        "entry_type": "boot",
        "kernel": "ubuntu-22.04/vmlinuz",
        "initrd": "ubuntu-22.04/initrd",
        "cmdline": "ip=dhcp",
        "enabled": true,
        "order": 1
      }
    ]
  }'
```

### Download Asset

```bash
curl -X POST http://localhost:9021/api/assets/download \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso",
    "dest": "ubuntu-22.04/ubuntu-22.04.5.iso"
  }'
```

### Extract ISO

```bash
curl -X POST http://localhost:9021/api/assets/extract-iso \
  -H "Content-Type: application/json" \
  -d '{
    "iso_path": "rescue/systemrescue-12.03-amd64.iso",
    "dest_dir": "rescue-12.03",
    "kernel_path": "sysresccd/boot/x86_64/vmlinuz",
    "initrd_path": "sysresccd/boot/x86_64/sysresccd.img"
  }'
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│  React Frontend (Vite + React 18)               │
│  ├─ Menu Builder (scenarios, drag-drop)         │
│  ├─ Asset Manager (downloads, progress)         │
│  ├─ DHCP Helper (multi-platform configs)        │
│  └─ Property Editor (smart fields)              │
└─────────────────┬───────────────────────────────┘
                  │ REST API
┌─────────────────┴───────────────────────────────┐
│  FastAPI Backend                                 │
│  ├─ iPXE Manager (validation, generation)       │
│  ├─ Asset Manager (download, extract)           │
│  ├─ DHCP Helper (config generation, validation) │
│  └─ File Serving (static files, iPXE scripts)   │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────┴───────────────────────────────┐
│  Storage (Docker Volumes)                        │
│  ├─ /srv/tftp  (TFTP boot files)                │
│  ├─ /srv/http  (HTTP assets)                    │
│  ├─ /srv/ipxe  (iPXE scripts)                   │
│  └─ /srv/dhcp  (DHCP configs)                   │
└──────────────────────────────────────────────────┘
```

## 🔍 Troubleshooting

### Downloads not working
- Check internet connectivity
- Verify disk space: `df -h`
- Check container logs: `docker-compose logs -f`

### DHCP validation fails
- Ensure container has `NET_ADMIN` capability (already in docker-compose.yml)
- Check network interface accessibility
- Validation is optional - config generation works without it

### PXE boot not working
1. Verify DHCP server configuration
2. Check TFTP files exist: `ls -la data/srv/tftp/`
3. Test iPXE script: `curl http://localhost:9021/ipxe/boot.ipxe`
4. Check firewall rules for ports 69 and 9021

### Progress bars disappear
- Fixed! Progress now persists across tab switches
- If issue persists: `docker-compose restart`

## 💡 Tips & Tricks

### Parallel Downloads
When downloading a distro with netboot + ISO:
- Kernel and initrd download in parallel
- ISO downloads after (to avoid saturating network)
- Total time savings: ~30-50%

### Asset Detection
The wizard automatically:
- Scans for downloaded versions
- Auto-populates kernel/initrd paths
- Suggests version in title
- Works for Ubuntu, Debian, SystemRescue

### Keyboard Shortcuts
- Builder: Select entry → edit in main area
- Category cards: Click to open wizard pre-selected
- Version selector: Auto-selects if only one version

## 📚 Documentation

- **API Docs**: http://localhost:9021/docs (Swagger UI)
- **Scenarios Reference**: See `frontend/src/data/scenarios.js`
- **DHCP Examples**: Check DHCP tab for your server type

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature-name`
3. Test your changes: `docker-compose up -d --build`
4. Commit: `git commit -m 'Add feature'`
5. Push: `git push origin feature-name`
6. Create Pull Request

## 📝 License

MIT License - see LICENSE file for details

## 🎯 Roadmap

- [x] Visual menu builder
- [x] Asset manager with parallel downloads
- [x] DHCP configuration helper
- [x] ISO extraction API
- [x] Smart asset detection in wizard
- [ ] Menu templates gallery
- [ ] Preseed/cloud-init editor
- [ ] Multi-language support
- [ ] Theme customization
- [ ] Webhook notifications
- [ ] Metrics dashboard

---

**Made with ❤️ by the iPXE Station Team**

🌟 Star us on GitHub: [loglux/ipxe-station](https://github.com/loglux/ipxe-station)

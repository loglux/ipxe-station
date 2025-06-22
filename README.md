# iPXE Station

**iPXE Station** is a modern PXE/iPXE server solution with multi-version Ubuntu support, featuring a web interface for managing boot resources and persistent storage.

## 🚀 Features

- **Multi-Version Ubuntu Support**: Download and manage multiple Ubuntu versions simultaneously
- **Persistent Storage**: Data survives container restarts using Docker volumes
- **Web Interface** (Gradio) for:
  - Downloading multiple Ubuntu versions (20.04, 22.04, 24.04)
  - Managing installed versions (view, delete, check status)
  - Creating and editing iPXE boot menus
  - Generating DHCP configurations
  - System monitoring and testing
- **FastAPI REST API** for automation and external integration
- **TFTP and HTTP file serving** with proper volume management
- **Auto-generation of iPXE menus** based on installed Ubuntu versions
- **Docker-ready** with volume support for persistent data

## 📋 Requirements

- **Docker** (recommended for deployment)
- **Python 3.12+** (for development)
- **Linux** (recommended for production)
- **Sufficient disk space** (each Ubuntu version ~2-3GB)

## 🚀 Quick Start

### Option 1: Using Deploy Script (Recommended)

```bash
git clone https://github.com/loglux/ipxe-station.git
cd ipxe-station
chmod +x deploy.sh
./deploy.sh
```

### Option 2: Using Docker Compose

```bash
git clone https://github.com/loglux/ipxe-station.git
cd ipxe-station
docker-compose up -d
```

### Option 3: Manual Docker

```bash
git clone https://github.com/loglux/ipxe-station.git
cd ipxe-station

# Create data directories
mkdir -p ./data/srv/{tftp,http,ipxe,dhcp}

# Build and run
docker build -t ipxe-station .
docker run -d \
  --name ipxe-station \
  -p 9005:8000 \
  -p 69:69/udp \
  -v ./data/srv/tftp:/srv/tftp \
  -v ./data/srv/http:/srv/http \
  -v ./data/srv/ipxe:/srv/ipxe \
  -v ./data/srv/dhcp:/srv/dhcp \
  --restart unless-stopped \
  ipxe-station
```

## 🌐 Access Points

- **Web UI**: [http://localhost:9005/gradio](http://localhost:9005/gradio)
- **Main Page**: [http://localhost:9005](http://localhost:9005)
- **API Status**: [http://localhost:9005/status](http://localhost:9005/status)
- **TFTP Server**: `localhost:69/UDP`

## 📁 Persistent Storage Structure

The new volume system creates persistent storage on your host:

```bash
./data/
└── srv/
    ├── tftp/           # TFTP boot files
    │   ├── undionly.kpxe
    │   ├── ipxe.efi
    │   └── README.txt
    ├── http/           # HTTP boot files (multi-version)
    │   ├── ubuntu-20.04/
    │   │   ├── vmlinuz
    │   │   ├── initrd
    │   │   └── preseed.cfg
    │   ├── ubuntu-22.04/
    │   │   ├── vmlinuz
    │   │   ├── initrd
    │   │   └── preseed.cfg
    │   ├── ubuntu-24.04/
    │   │   ├── vmlinuz
    │   │   ├── initrd
    │   │   └── preseed.cfg
    │   └── iso/        # ISO storage
    ├── ipxe/           # iPXE scripts
    │   ├── boot.ipxe
    │   └── README.txt
    └── dhcp/           # DHCP configurations
        ├── dhcpd.conf
        ├── dnsmasq.conf
        └── mikrotik_commands.txt
```

## 🔧 Usage

### 1. Download Ubuntu Versions

1. Open Web UI → **Ubuntu Download** tab
2. Select version (20.04, 22.04, or 24.04)
3. Click **Download Ubuntu Files**
4. Monitor progress and status

### 2. Manage Installed Versions

- **View all versions**: Click **Check All Versions**
- **Check specific version**: Select from dropdown, click **Check Version**
- **Delete version**: Select version, click **Delete Version**
- **View summary**: Automatic summary shows installed vs available versions

### 3. Create iPXE Menus

1. Go to **iPXE Menu** tab
2. Select **ubuntu** template
3. Click **Create from Template** (automatically includes all installed Ubuntu versions)
4. Customize if needed
5. Click **Save Menu**

### 4. Configure DHCP

1. Go to **DHCP Configuration** tab
2. Enter network settings
3. Select DHCP server type (ISC, dnsmasq, MikroTik)
4. Click **Generate Config**
5. Copy configuration to your DHCP server

### 5. Test System

1. Go to **System Testing** tab
2. Run **Full System Test** to verify all components
3. Use manual testing tools for specific checks

## 📊 Management Commands

### Deploy Script Commands

```bash
./deploy.sh deploy    # Deploy with volumes
./deploy.sh stop      # Stop container
./deploy.sh start     # Start container
./deploy.sh restart   # Restart container
./deploy.sh logs      # View logs
./deploy.sh status    # Show status
./deploy.sh info      # Show volume information
./deploy.sh backup    # Create data backup
./deploy.sh restore   # Restore from backup
./deploy.sh remove    # Remove container (keep data)
```

### Docker Compose Commands

```bash
docker-compose up -d       # Start services
docker-compose down        # Stop services
docker-compose logs -f     # View logs
docker-compose restart     # Restart services
```

## 💾 Data Management

### Backup Data

```bash
# Using deploy script
./deploy.sh backup

# Manual backup
tar -czf ipxe-backup-$(date +%Y%m%d).tar.gz ./data
```

### Restore Data

```bash
# Using deploy script
./deploy.sh restore ipxe-backup-20241220.tar.gz

# Manual restore
tar -xzf ipxe-backup-20241220.tar.gz
```

### Check Storage Usage

```bash
# View volume information
./deploy.sh info

# Check disk usage
du -sh ./data/
```

## 🔧 Advanced Configuration

### Environment Variables

- `PXE_SERVER_IP`: Server IP address (default: auto-detect)
- `HTTP_PORT`: HTTP server port (default: 8000)
- `TFTP_PORT`: TFTP server port (default: 69)

### Custom Volume Paths

Modify `docker-compose.yml` or deploy script to use different paths:

```yaml
volumes:
  - /custom/path/tftp:/srv/tftp:rw
  - /custom/path/http:/srv/http:rw
```

## 🏗️ Project Structure

```
ipxe-station/
├── app/                    # Application code
│   ├── main.py            # FastAPI application
│   ├── gradio_ui.py       # Web interface
│   ├── ubuntu_downloader.py  # Multi-version Ubuntu handler
│   ├── ipxe_manager.py    # iPXE menu management
│   ├── dhcp_config.py     # DHCP configuration
│   ├── system_status.py   # System monitoring
│   └── tests.py           # System testing
├── scripts/                # Container scripts
│   ├── setup-volumes.sh   # Volume initialization
│   └── start.sh           # Container startup
├── data/                   # Persistent data (created on first run)
│   └── srv/               # Volume mount points
├── Dockerfile             # Container definition
├── docker-compose.yml     # Compose configuration
├── deploy.sh              # Deployment script
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

## 🔍 Troubleshooting

### Common Issues

1. **Port 69 UDP in use**
   - Check if another TFTP server is running
   - Use different port or stop conflicting service

2. **Permission issues with volumes**
   - Ensure Docker has access to the data directory
   - Check file permissions: `chmod -R 755 ./data`

3. **Large downloads failing**
   - Check disk space: `df -h`
   - Ensure stable internet connection
   - Downloads can be resumed by restarting

4. **Container not starting**
   - Check logs: `./deploy.sh logs`
   - Verify port availability
   - Check Docker daemon status

### Debug Commands

```bash
# Check container status
docker ps -a

# View detailed logs
docker logs -f ipxe-station

# Enter container for debugging
docker exec -it ipxe-station bash

# Check volume mounts
docker inspect ipxe-station | grep -A 10 "Mounts"
```

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature-name`
3. Make changes and test
4. Commit: `git commit -am 'Add feature'`
5. Push: `git push origin feature-name`
6. Create Pull Request

## 📝 License

MIT License - see LICENSE file for details

## 🎯 Roadmap

- [ ] User authentication and authorization
- [ ] REST API for Ubuntu version management
- [ ] Integration with cloud storage (S3, GCS)
- [ ] Support for other Linux distributions
- [ ] Web-based file manager
- [ ] Automatic Ubuntu version updates
- [ ] Metrics and monitoring dashboard

---

**Author:** [iPXE Station Team](https://github.com/loglux/ipxe-station)
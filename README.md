# ipxe-station

**ipxe-station** is a modern PXE/iPXE server solution featuring a web interface for managing boot resources (ISOs, kernels, initrds, and iPXE scripts) and quick setup via browser.

## Features

- Web interface (Gradio) for:
  - Uploading, deleting, and listing boot files
  - Managing iPXE scripts (create/edit menu)
- FastAPI REST API for automation or external integration
- TFTP (tftpd-hpa) and HTTP file serving
- Ready-to-use Docker container

## Requirements

- Python 3.12 or higher
- Gradio 5.33.0 or higher
- Docker (recommended for deployment)
- Linux (recommended for production use)

## Quick Start

```bash
git clone https://github.com/yourusername/ipxe-station.git
cd ipxe-station
docker build -t ipxe-station .
docker run -it -p 7860:7860 -p 8000:8000 -p 69:69/udp -v $PWD/srv:/srv ipxe-station
```

- Gradio UI: [http://localhost:7860](http://localhost:7860)
- FastAPI docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- PXE/TFTP: UDP port 69

## Roadmap / TODO

- [ ] User authentication
- [ ] DHCP/BOOTP configuration helper
- [ ] iPXE menu templates support
- [ ] Notifications/logging

## Project Structure

ipxe-station/
│
├── app/
│   ├── main.py           # FastAPI app with Gradio UI mount
│   ├── gradio_ui.py      # Gradio Blocks UI (upload/list/delete)
│   ├── file_utils.py     # Utilities for file operations
│   └── requirements.txt  # Python dependencies
│
├── Dockerfile            # Docker build file
├── tftpd-hpa             # TFTP server config
├── srv/
│   ├── tftp/             # Directory for TFTP files (e.g. ipxe.efi)
│   ├── http/             # Directory for HTTP-accessible resources
│   ├── ipxe/             # iPXE scripts
│   └── uploads/          # Temporary uploads (if needed)
│
├── .gitignore
├── README.md


## License

MIT

---

**Author:** [yourusername](https://github.com/yourusername)

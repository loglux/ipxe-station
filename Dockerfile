FROM python:3.12-slim

# Install ALL needed system tools
RUN apt-get update && \
    apt-get install -y \
        # TFTP server
        tftpd-hpa \
        # Syslog
        rsyslog \
        # Download tools
        wget curl \
        # ISO/Archive tools
        p7zip-full unzip gzip cpio \
        # SquashFS tools (merge layers for Ubuntu Server netboot)
        squashfs-tools \
        # Mount tools
        mount util-linux \
        # File system tools
        file tree \
        # System tools
        sudo procps \
        # NFS client tools (showmount for NFS status check)
        nfs-common \
        # Proxy DHCP
        dnsmasq \
        # Debug tools (optional)
        htop nano \
        && \
    rm -rf /var/lib/apt/lists/*

# Set working directory to parent of app
WORKDIR /

# Set Python path to include root so 'app.backend' imports work
ENV PYTHONPATH=/

# Copy application files to /app (preserving the app/ structure)
COPY app/ /app/
COPY tftpd-hpa /etc/default/tftpd-hpa
# Note: frontend dist is now built into app/frontend/dist/ (see vite.config.js outDir)
# and is included by the COPY app/ above — no separate COPY needed.

# Install Python dependencies
COPY requirements.txt /
RUN pip install --no-cache-dir -r requirements.txt

# Create volume mount points with proper permissions
# These directories will be mounted as volumes from host
RUN mkdir -p /srv/tftp /srv/http /srv/ipxe /srv/dhcp && \
    chmod 755 /srv/tftp /srv/http /srv/ipxe /srv/dhcp

# Create working directories
RUN mkdir -p /mnt/iso /tmp/extract && \
    chmod 755 /mnt/iso /tmp/extract

# Download iPXE binaries — stored outside /app so volume-mount of ./app doesn't shadow them
RUN mkdir -p /opt/ipxe-initial-files/tftp && \
    cd /opt/ipxe-initial-files/tftp && \
    wget -q http://boot.ipxe.org/undionly.kpxe && \
    wget -q -O ipxe.efi http://boot.ipxe.org/x86_64-efi/ipxe.efi && \
    wget -q -O snponly.efi http://boot.ipxe.org/x86_64-efi/snponly.efi && \
    wget -q http://boot.ipxe.org/ipxe.pxe && \
    ls -la /opt/ipxe-initial-files/tftp/

# Copy setup and startup scripts to /usr/local/bin so ./app:/app mount doesn't shadow them
COPY scripts/setup-volumes.sh /usr/local/bin/setup-volumes.sh
COPY scripts/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/setup-volumes.sh /usr/local/bin/start.sh

# Configure sudo for volume operations
RUN echo 'root ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers

# Expose ports
EXPOSE 69/udp 9021 9005

# Change working directory back to /app for running the application
WORKDIR /app

# Use the startup script as entrypoint
CMD ["/usr/local/bin/start.sh"]

# Volume declarations for documentation
VOLUME ["/srv/tftp", "/srv/http", "/srv/ipxe", "/srv/dhcp"]

# Health check
# Uses UVICORN_PORT (default 9021) for health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9021/status || exit 1

# Labels for metadata
LABEL maintainer="iPXE Station Team"
LABEL description="PXE Boot Station with multi-version Ubuntu support"
LABEL version="2.0"

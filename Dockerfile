FROM python:3.12-slim

# Install ALL needed system tools
RUN apt-get update && \
    apt-get install -y \
        # TFTP server
        tftpd-hpa \
        # Syslog \
        rsyslog \
        # Download tools
        wget curl \
        # ISO/Archive tools
        p7zip-full unzip gzip cpio \
        # Mount tools
        mount util-linux \
        # File system tools
        file tree \
        # System tools
        sudo procps \
        # Debug tools (optional)
        htop nano \
        && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Set Python path to include /app so imports work correctly
ENV PYTHONPATH=/app

# Copy application files
COPY app/ /app/
COPY tftpd-hpa /etc/default/tftpd-hpa

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create volume mount points with proper permissions
# These directories will be mounted as volumes from host
RUN mkdir -p /srv/tftp /srv/http /srv/ipxe /srv/dhcp && \
    chmod 755 /srv/tftp /srv/http /srv/ipxe /srv/dhcp

# Create working directories
RUN mkdir -p /mnt/iso /tmp/extract && \
    chmod 755 /mnt/iso /tmp/extract

# Download iPXE binaries to temporary location (will be copied to volume on first run)
RUN mkdir -p /app/initial-files/tftp && \
    cd /app/initial-files/tftp && \
    wget -q http://boot.ipxe.org/undionly.kpxe && \
    wget -q http://boot.ipxe.org/ipxe.efi && \
    wget -q http://boot.ipxe.org/ipxe.pxe && \
    ls -la /app/initial-files/tftp/

# Copy setup and startup scripts
COPY scripts/setup-volumes.sh /app/
COPY scripts/start.sh /app/
RUN chmod +x /app/setup-volumes.sh /app/start.sh

# Configure sudo for volume operations
RUN echo 'root ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers

# Expose ports
EXPOSE 69/udp 8000 9005

# Use the startup script as entrypoint
CMD ["/app/start.sh"]

# Volume declarations for documentation
VOLUME ["/srv/tftp", "/srv/http", "/srv/ipxe", "/srv/dhcp"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/status || exit 1

# Labels for metadata
LABEL maintainer="iPXE Station Team"
LABEL description="PXE Boot Station with multi-version Ubuntu support"
LABEL version="2.0"
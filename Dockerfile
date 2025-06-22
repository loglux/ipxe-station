
FROM python:3.12-slim

# Install ALL needed system tools
RUN apt-get update && \
    apt-get install -y \
        # TFTP server
        tftpd-hpa \
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
        # Debug tools (опционально)
        htop nano \
        && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application files
COPY app/ /app/
COPY tftpd-hpa /etc/default/tftpd-hpa
COPY srv/ /srv/

# Install Python dependencies (mininum)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directories with proper permissions
RUN mkdir -p /srv/tftp /srv/http /srv/ipxe /mnt/iso /tmp/extract && \
    chmod 755 /srv/tftp /srv/http /srv/ipxe /mnt/iso /tmp/extract

# Download iPXE binaries
RUN cd /srv/tftp && \
    wget -q http://boot.ipxe.org/undionly.kpxe && \
    wget -q http://boot.ipxe.org/ipxe.efi && \
    ls -la /srv/tftp/

# Configure sudo
RUN echo 'root ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers

# Expose ports
EXPOSE 69/udp 8000 9005

# Start services
CMD ["sh", "-c", "service tftpd-hpa start && python main.py"]
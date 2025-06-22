
FROM python:3.12-slim

# Install system dependencies INCLUDING ISO tools
RUN apt-get update && \
    apt-get install -y \
        tftpd-hpa \
        wget \
        curl \
        p7zip-full \
        unzip \
        mount \
        sudo \
        cpio \
        gzip \
        file \
        && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application files
COPY app/ /app/
COPY tftpd-hpa /etc/default/tftpd-hpa
COPY srv/ /srv/

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directories with proper permissions
RUN mkdir -p /srv/tftp /srv/http /srv/ipxe /mnt/iso && \
    chmod 755 /srv/tftp /srv/http /srv/ipxe /mnt/iso

# Download iPXE binaries
RUN cd /srv/tftp && \
    wget -q http://boot.ipxe.org/undionly.kpxe && \
    wget -q http://boot.ipxe.org/ipxe.efi && \
    ls -la /srv/tftp/

# Configure sudo for root (needed for ISO mounting in Docker)
RUN echo 'root ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers

# Expose ports
EXPOSE 69/udp 8000 9005

# Start services with proper signal handling
CMD ["sh", "-c", "service tftpd-hpa start && python main.py"]
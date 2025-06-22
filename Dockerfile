FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y tftpd-hpa wget curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application files
COPY app/ /app/
COPY tftpd-hpa /etc/default/tftpd-hpa
COPY srv/ /srv/

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directories
RUN mkdir -p /srv/tftp /srv/http /srv/ipxe

# Download iPXE binaries (это ОСНОВА сервера!)
RUN cd /srv/tftp && \
    wget -q http://boot.ipxe.org/undionly.kpxe && \
    wget -q http://boot.ipxe.org/ipxe.efi && \
    ls -la /srv/tftp/

# Expose ports
EXPOSE 69/udp 8000 9005

# Start services - JSON формат для корректной обработки сигналов
CMD ["sh", "-c", "service tftpd-hpa start && python main.py"]
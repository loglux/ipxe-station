"""Centralised configuration with environment overrides."""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    pxe_server_ip: str = os.getenv("PXE_SERVER_IP", "192.168.1.1")  # Common router IP as default
    nfs_root: str = os.getenv("NFS_ROOT", "/srv/nfs")
    http_port: int = int(os.getenv("HTTP_PORT", "9021"))


# Export a singleton and legacy constants for backwards compatibility
settings = Settings()
PXE_SERVER_IP = settings.pxe_server_ip
NFS_ROOT = settings.nfs_root
HTTP_PORT = settings.http_port

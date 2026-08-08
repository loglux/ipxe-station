"""Centralised configuration with environment overrides."""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    pxe_server_ip: str = os.getenv("PXE_SERVER_IP", "192.168.1.1")  # Common router IP as default
    nfs_root: str = os.getenv("NFS_ROOT", "/srv/nfs")
    http_port: int = int(os.getenv("HTTP_PORT", "9021"))
    # Security mode is intentionally env-only (not exposed via /api/settings) so an
    # unauthenticated request can never flip auth off at runtime.
    security_mode: str = os.getenv("SECURITY_MODE", "off").strip().lower()
    api_token: str = os.getenv("API_TOKEN", "").strip()


# Export a singleton and legacy constants for backwards compatibility
settings = Settings()
PXE_SERVER_IP = settings.pxe_server_ip
NFS_ROOT = settings.nfs_root
HTTP_PORT = settings.http_port

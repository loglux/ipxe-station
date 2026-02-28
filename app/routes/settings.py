"""Settings and network detection routes."""

from fastapi import APIRouter

from .state import SettingsModel, load_settings, save_settings

settings_router = APIRouter(tags=["settings"])


@settings_router.get("/api/settings")
def get_settings():
    """Get current settings."""
    return load_settings().model_dump()


@settings_router.post("/api/settings")
def update_settings(settings: SettingsModel):
    """Update and save settings."""
    save_settings(settings)
    return {"success": True, "settings": settings.model_dump()}


@settings_router.get("/api/network/detect")
def detect_network():
    """Auto-detect server IP address."""
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()

        hostname = socket.gethostname()
        all_ips = socket.gethostbyname_ex(hostname)[2]

        return {"detected_ip": ip_address, "hostname": hostname, "all_ips": all_ips}
    except Exception as e:
        return {
            "detected_ip": "127.0.0.1",
            "hostname": "localhost",
            "all_ips": ["127.0.0.1"],
            "error": str(e),
        }

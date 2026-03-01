"""Proxy DHCP server routes (dnsmasq-based)."""

from fastapi import APIRouter, HTTPException

from app.backend.proxy_dhcp import ProxyDHCPManager, ProxyDHCPSettings
from app.routes.state import add_log

proxy_dhcp_router = APIRouter(prefix="/api/proxy-dhcp", tags=["proxy-dhcp"])
_manager = ProxyDHCPManager()


@proxy_dhcp_router.get("/status")
def get_proxy_dhcp_status():
    """Return running state and current settings of the Proxy DHCP server."""
    return _manager.get_status()


@proxy_dhcp_router.post("/start")
def start_proxy_dhcp(settings: ProxyDHCPSettings):
    """Save settings and start the Proxy DHCP server.

    Settings from the request body are merged over the saved/default settings,
    so the real server IP is always populated even if the body omits it.
    """
    try:
        effective = _manager.load_settings().model_copy(
            update=settings.model_dump(exclude_unset=True)
        )
        _manager.save_settings(effective)
        result = _manager.start(effective)
        if result["success"]:
            add_log("dhcp", "info", f"Proxy DHCP started (pid {result.get('pid')})")
        else:
            add_log("dhcp", "error", f"Proxy DHCP failed to start: {result.get('error')}")
            raise HTTPException(status_code=500, detail=result.get("error", "Start failed"))
        return result
    except HTTPException:
        raise
    except Exception as exc:
        add_log("dhcp", "error", f"Proxy DHCP start error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@proxy_dhcp_router.post("/stop")
def stop_proxy_dhcp():
    """Stop the Proxy DHCP server."""
    try:
        result = _manager.stop()
        if result["success"]:
            add_log("dhcp", "info", "Proxy DHCP stopped")
        else:
            add_log("dhcp", "warning", f"Proxy DHCP stop issue: {result.get('error')}")
        return result
    except Exception as exc:
        add_log("dhcp", "error", f"Proxy DHCP stop error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@proxy_dhcp_router.get("/config")
def get_proxy_dhcp_config():
    """Return the persisted Proxy DHCP settings."""
    return _manager.load_settings().model_dump()


@proxy_dhcp_router.post("/config")
def save_proxy_dhcp_config(settings: ProxyDHCPSettings):
    """Persist Proxy DHCP settings without restarting the server."""
    try:
        _manager.save_settings(settings)
        add_log("dhcp", "info", "Proxy DHCP settings saved")
        return {"success": True}
    except Exception as exc:
        add_log("dhcp", "error", f"Failed to save Proxy DHCP config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

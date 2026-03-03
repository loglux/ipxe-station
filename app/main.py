import logging
import os
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.routes.assets import assets_router
from app.routes.boot import boot_router
from app.routes.dhcp import dhcp_router
from app.routes.ipxe import ipxe_router
from app.routes.monitoring import monitoring_router, syslog_monitor_thread
from app.routes.proxy_dhcp import proxy_dhcp_router
from app.routes.settings import settings_router
from app.routes.state import (
    HTTP_ROOT,
    IPXE_ROOT,
    PXE_CLIENTS,  # noqa: F401 — re-exported for test imports
    SYSTEM_LOGS,  # noqa: F401 — re-exported for test imports
    TFTP_ROOT,
    _record_http_boot_flow,
    _refresh_boot_sessions,  # noqa: F401 — re-exported for test imports
    _track_ipxe_loop,  # noqa: F401 — re-exported for test imports
    add_log,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="iPXE Station", description="Network Boot Server")


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log HTTP requests to monitoring system."""
    if not request.url.path.startswith("/api/monitoring"):
        from datetime import datetime

        start_time = datetime.now()
        response = await call_next(request)
        _record_http_boot_flow(request, request.url.path, response.status_code)

        if not request.url.path.startswith(("/ui/", "/status")):
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000

            level = "info"
            if response.status_code >= 400:
                level = "warning" if response.status_code < 500 else "error"

            message = (
                f"{request.method} {request.url.path}"
                f" - {response.status_code} ({duration_ms:.0f}ms)"
            )
            if request.client:
                message = f"{request.client.host} - {message}"

            add_log("http", level, message)

        return response
    else:
        return await call_next(request)


# ---------------------------------------------------------------------------
# Static file mounts
# ---------------------------------------------------------------------------

app.mount("/http", StaticFiles(directory=str(HTTP_ROOT)), name="http")


# ---------------------------------------------------------------------------
# Core routes (file serving and status)
# ---------------------------------------------------------------------------


@app.get("/ipxe/{filename}")
@app.head("/ipxe/{filename}")
async def serve_ipxe(filename: str):
    """Serve iPXE files."""
    try:
        file_path = (IPXE_ROOT / filename).resolve()
        file_path.relative_to(IPXE_ROOT.resolve())
        if file_path.exists():
            return FileResponse(
                file_path, media_type="text/plain", headers={"Cache-Control": "no-cache"}
            )
    except (ValueError, OSError):
        pass
    return Response("File not found", status_code=404)


@app.get("/tftp/{filename}")
async def serve_tftp(filename: str):
    """Serve TFTP files via HTTP."""
    try:
        file_path = (TFTP_ROOT / filename).resolve()
        file_path.relative_to(TFTP_ROOT.resolve())
        if file_path.exists():
            return FileResponse(file_path)
    except (ValueError, OSError):
        pass
    return Response("File not found", status_code=404)


@app.get("/")
async def root():
    """Redirect to React UI."""
    return RedirectResponse(url="/ui")


@app.get("/status")
async def status():
    """Server status."""
    return {
        "tftp_files": len(list(TFTP_ROOT.glob("*"))),
        "http_files": len(list(HTTP_ROOT.rglob("*"))),
        "ipxe_files": len(list(IPXE_ROOT.glob("*"))),
    }


# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------

app.include_router(ipxe_router)
app.include_router(boot_router)
app.include_router(assets_router)
app.include_router(dhcp_router)
app.include_router(proxy_dhcp_router)
app.include_router(monitoring_router)
app.include_router(settings_router)


# ---------------------------------------------------------------------------
# Background tasks and startup
# ---------------------------------------------------------------------------

monitor_thread = threading.Thread(target=syslog_monitor_thread, daemon=True)
monitor_thread.start()

add_log("system", "info", "iPXE Station monitoring initialised")
add_log("system", "info", "TFTP log integration started")


# Auto-start proxy DHCP if it was enabled when the container last ran.
def _autostart_proxy_dhcp():
    try:
        from app.routes.proxy_dhcp import _manager as _proxy_manager

        s = _proxy_manager.load_settings()
        if s.enabled:
            result = _proxy_manager.start(s)
            if result.get("success"):
                add_log("dhcp", "info", f"Proxy DHCP auto-started (pid {result.get('pid')})")
            else:
                add_log("dhcp", "warning", f"Proxy DHCP auto-start failed: {result.get('error')}")
    except Exception as exc:
        add_log("dhcp", "warning", f"Proxy DHCP auto-start error: {exc}")


_autostart_proxy_dhcp()


def _proxy_dhcp_watchdog():
    """Restart dnsmasq if it should be running but has died."""
    import time

    from app.routes.proxy_dhcp import _manager as _proxy_manager

    while True:
        time.sleep(30)
        try:
            s = _proxy_manager.load_settings()
            if s.enabled and not _proxy_manager.is_running():
                add_log("dhcp", "warning", "Proxy DHCP died — restarting automatically")
                result = _proxy_manager.start(s)
                if result.get("success"):
                    add_log("dhcp", "info", f"Proxy DHCP restarted (pid {result.get('pid')})")
                else:
                    add_log("dhcp", "error", f"Proxy DHCP restart failed: {result.get('error')}")
        except Exception as exc:
            add_log("dhcp", "warning", f"Proxy DHCP watchdog error: {exc}")


threading.Thread(target=_proxy_dhcp_watchdog, daemon=True, name="proxy-dhcp-watchdog").start()


# ---------------------------------------------------------------------------
# Frontend (Vite SPA)
# ---------------------------------------------------------------------------

FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="ui")
else:
    logger.warning("Frontend dist directory not found. Build the frontend first.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting server...")
    port = int(os.getenv("UVICORN_PORT", "9021"))
    host = os.getenv("UVICORN_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)

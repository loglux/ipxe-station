import logging
import os
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.backend import boot_report, krd_display, krd_schedule
from app.routes.assets import assets_router
from app.routes.boot import boot_router
from app.routes.boot_reports import boot_reports_router, reports_file
from app.routes.boundary import api_boundary_context
from app.routes.dhcp import dhcp_router
from app.routes.ipxe import build_personal_menu_script, ipxe_router
from app.routes.kaspersky import (
    MAX_REPORT_BYTES,
    display_settings,
    kaspersky_router,
    record_firmware_report,
    schedule_loop,
)
from app.routes.monitoring import monitoring_router, syslog_monitor_thread
from app.routes.proxy_dhcp import proxy_dhcp_router
from app.routes.scenarios import scenarios_router
from app.routes.settings import settings_router
from app.routes.state import (
    HTTP_ROOT,
    IPXE_ROOT,
    PXE_CLIENTS,  # noqa: F401 — re-exported for test imports
    SYSTEM_LOGS,  # noqa: F401 — re-exported for test imports
    TFTP_ROOT,
    _normalise_inventory,
    _record_http_boot_flow,
    _refresh_boot_sessions,  # noqa: F401 — re-exported for test imports
    _track_ipxe_loop,  # noqa: F401 — re-exported for test imports
    add_log,
    record_client_inventory,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="iPXE Station", description="Network Boot Server")


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


def _is_quiet_request(request: Request, status_code: int) -> bool:
    """True for requests that are not worth a monitoring-log line.

    The UI polls several GET /api/* endpoints every few seconds; logging each successful
    poll buries real boot activity. Failures, API writes and boot-file requests stay visible.
    """
    path = request.url.path
    if path == "/ui" or path.startswith(("/ui/", "/status", "/client-info")):
        return True
    return request.method == "GET" and path.startswith("/api/") and status_code < 400


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log HTTP requests to monitoring system."""
    if not request.url.path.startswith("/api/monitoring"):
        from datetime import datetime

        start_time = datetime.now()
        response = await call_next(request)
        _record_http_boot_flow(request, request.url.path, response.status_code)

        if not _is_quiet_request(request, response.status_code):
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


_CLIENT_INFO_FIELDS = (
    "mac",
    "uuid",
    "manufacturer",
    "product",
    "sku",
    "family",
    "serial",
    "asset",
    "bios_version",
    "bios_date",
    "platform",
    "arch",
    "busid",
    "chip",
    "ipxe",
)


@app.get("/ipxe/menu")
async def personal_menu(request: Request):
    """Build the boot menu for the machine that asks, and record what it reports about itself.

    Open like boot.ipxe: iPXE cannot present an API token. ``preview=1`` builds the menu
    without recording the machine (for testing).
    """
    fields = {name: request.query_params.get(name, "")[:200] for name in _CLIENT_INFO_FIELDS}
    client_ip = request.client.host if request.client else "unknown"
    if request.query_params.get("preview") == "1":
        device = _normalise_inventory(fields)
    else:
        device = record_client_inventory(client_ip, fields) or _normalise_inventory(fields)
    script = build_personal_menu_script(device)
    if script is None:
        return Response("No menu saved yet", status_code=404)
    return Response(script, media_type="text/plain", headers={"Cache-Control": "no-cache"})


@app.get(krd_display.HOOK_PATH)
async def krd_display_hook(request: Request):
    """The text-size script for a Kaspersky Rescue Disk that is booting; open like boot.ipxe."""
    fields = {
        name: request.query_params.get(name, "")[:200] for name in krd_display.HOOK_QUERY_FIELDS
    }
    device = _normalise_inventory(fields)
    krd_schedule.note_boot()
    scale, source = krd_display.resolve_scale(display_settings(), device)
    add_log(
        "system",
        "info",
        f"Kaspersky text size for {fields.get('product') or 'a machine'}: {scale} ({source})",
    )
    settings = display_settings()
    report_url = ""
    if settings.report_firmware:
        report_url = krd_display.report_url_for(request.headers.get("host", ""), device)
    return Response(
        krd_display.render_hook(scale, report_url),
        media_type="text/x-shellscript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get(boot_report.HOOK_PATH)
async def live_report_hook(request: Request):
    """The boot-report script for a live system that is starting; open like boot.ipxe."""
    fields = {
        name: request.query_params.get(name, "")[:200] for name in boot_report.HOOK_QUERY_FIELDS
    }
    device = _normalise_inventory(fields)
    url = boot_report.report_url_for(request.headers.get("host", ""), device)
    return Response(
        boot_report.render_hook(url),
        media_type="text/x-shellscript",
        headers={"Cache-Control": "no-cache"},
    )


@app.post(boot_report.REPORT_PATH)
async def live_boot_report(request: Request):
    """What a live system reports about itself once it is up; open, size-limited, cleaned."""
    body = await request.body()
    if len(body) > boot_report.MAX_BODY_BYTES:
        return Response("Report too large", status_code=413)
    fields = {
        name: request.query_params.get(name, "")[:200] for name in boot_report.HOOK_QUERY_FIELDS
    }
    client = request.client.host if request.client else ""
    entry = boot_report.record(
        reports_file(), client, _normalise_inventory(fields), body.decode("utf-8", "replace")
    )
    who = entry["device"] or client
    add_log(
        "system", "info", f"Boot report from {who}: {entry['summary']['os'] or 'a live system'}"
    )
    return Response(status_code=204)


@app.post(krd_display.REPORT_PATH)
async def krd_report(request: Request):
    """Missing-firmware lines a booting Kaspersky Rescue Disk sends; open like the script itself."""
    body = await request.body()
    if len(body) > MAX_REPORT_BYTES:
        return Response("Report too large", status_code=413)
    fields = {
        name: request.query_params.get(name, "")[:200] for name in krd_display.HOOK_QUERY_FIELDS
    }
    client = request.client.host if request.client else ""
    record_firmware_report(client, _normalise_inventory(fields), body.decode("utf-8", "replace"))
    return Response(status_code=204)


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


@app.get("/client-info")
async def client_info(request: Request):
    """Receive the machine details an iPXE script reports about itself.

    Open on purpose: iPXE cannot present a token. Every value is length-limited and cleaned before
    it reaches the log or the client list, and the list is capped.
    """
    fields = {name: request.query_params.get(name, "")[:200] for name in _CLIENT_INFO_FIELDS}
    client_ip = request.client.host if request.client else "unknown"
    record_client_inventory(client_ip, fields)
    return Response("ok", media_type="text/plain", headers={"Cache-Control": "no-cache"})


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


@app.get("/preseed.cfg")
@app.head("/preseed.cfg")
async def serve_preseed():
    """Serve Debian preseed configuration from HTTP root."""
    preseed_path = HTTP_ROOT / "preseed.cfg"
    if preseed_path.exists():
        return FileResponse(
            preseed_path, media_type="text/plain", headers={"Cache-Control": "no-cache"}
        )
    return Response("File not found", status_code=404)


@app.get("/preseed/{profile}.cfg")
@app.head("/preseed/{profile}.cfg")
async def serve_preseed_profile(profile: str):
    """Serve a named Debian preseed profile from HTTP root."""
    try:
        file_path = (HTTP_ROOT / "preseed" / f"{profile}.cfg").resolve()
        file_path.relative_to((HTTP_ROOT / "preseed").resolve())
        if file_path.exists():
            return FileResponse(
                file_path, media_type="text/plain", headers={"Cache-Control": "no-cache"}
            )
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

_api_routers = (
    ipxe_router,
    boot_router,
    assets_router,
    dhcp_router,
    proxy_dhcp_router,
    monitoring_router,
    settings_router,
    scenarios_router,
    kaspersky_router,
    boot_reports_router,
)
for _router in _api_routers:
    app.include_router(_router, dependencies=[Depends(api_boundary_context)])


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
threading.Thread(target=schedule_loop, daemon=True, name="krd-schedule").start()


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

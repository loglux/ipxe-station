"""Monitoring routes: logs, boot sessions, services, metrics, and syslog integration."""

import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.backend.proxy_dhcp import ProxyDHCPManager

from .state import (
    BASE_ROOT,
    SYSTEM_LOGS,
    _record_boot_event,
    _refresh_boot_sessions,
    _track_ipxe_loop,
    add_log,
    download_progress,
    download_progress_lock,
)

monitoring_router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

# Syslog tail state
syslog_position = 0
syslog_monitor_running = False


def parse_syslog_tftp():
    """Parse syslog for TFTP and dnsmasq-dhcp entries and add to monitoring."""
    global syslog_position
    import re
    from pathlib import Path

    syslog_path = Path("/var/log/syslog")
    if not syslog_path.exists():
        return

    try:
        with open(syslog_path, "r") as f:
            f.seek(syslog_position)

            for line in f:
                if "dnsmasq-dhcp" in line:
                    # e.g. "dnsmasq-dhcp[123]: DHCPDISCOVER(eth0) 192.168.10.37 00:50:56:xx"
                    message = re.sub(r"^.*dnsmasq-dhcp\[\d+\]:\s*", "", line).strip()
                    level = "info"
                    if "DHCPOFFER" in message or "PXEBOOT" in message:
                        level = "info"
                    elif "error" in message.lower() or "failed" in message.lower():
                        level = "error"
                    add_log("dhcp", level, message)
                    continue

                if "in.tftpd" in line:
                    message = line.split("in.tftpd", 1)[-1]
                    message = message.split("]: ", 1)[-1].strip()

                    rrq_match = re.search(r"RRQ from (\S+) filename (\S+)", message)
                    if rrq_match:
                        client_ip = rrq_match.group(1)
                        filename = rrq_match.group(2)
                        add_log(
                            "tftp",
                            "info",
                            f"Download request from {client_ip}: {filename}",
                            client_ip=client_ip,
                            filename=filename,
                            protocol="tftp",
                        )

                        if filename == "ipxe.efi":
                            _record_boot_event(
                                client_ip,
                                "ipxe_binary",
                                f"Served iPXE UEFI binary via TFTP: {filename}",
                                protocol="tftp",
                                filename=filename,
                            )
                            _track_ipxe_loop(client_ip, filename)
                        elif filename == "undionly.kpxe":
                            _record_boot_event(
                                client_ip,
                                "ipxe_binary",
                                f"Served iPXE BIOS binary via TFTP: {filename}",
                                protocol="tftp",
                                filename=filename,
                            )
                        elif filename.endswith(".ipxe"):
                            _record_boot_event(
                                client_ip,
                                "boot_script_tftp",
                                f"Served boot script via TFTP: {filename}",
                                protocol="tftp",
                                filename=filename,
                            )
                        continue

                    option_match = re.search(r"tftp: (.+)", message)
                    if option_match:
                        detail = option_match.group(1)
                        level = "debug"
                        if "does not accept options" in detail:
                            level = "info"
                        add_log("tftp", level, detail, protocol="tftp")
                    else:
                        add_log("tftp", "debug", message, protocol="tftp")

            syslog_position = f.tell()
    except Exception as e:
        import logging

        logging.getLogger(__name__).error("Error parsing syslog: %s", e)


def syslog_monitor_thread():
    """Background thread to monitor syslog."""
    global syslog_monitor_running
    syslog_monitor_running = True

    while syslog_monitor_running:
        parse_syslog_tftp()
        time.sleep(2)


@monitoring_router.get("/logs")
async def get_logs(type: str = None, level: str = None, limit: int = 100):
    """Get system logs with optional filtering."""
    try:
        _refresh_boot_sessions()
        filtered_logs = list(SYSTEM_LOGS)

        if type and type != "all":
            filtered_logs = [log for log in filtered_logs if log.get("type") == type]

        if level and level != "all":
            filtered_logs = [log for log in filtered_logs if log.get("level") == level]

        return {
            "logs": filtered_logs[-limit:],
            "total": len(filtered_logs),
            "filtered": len(filtered_logs),
        }
    except Exception as e:
        return {"logs": [], "total": 0, "error": str(e)}


@monitoring_router.get("/logs/download")
async def download_logs(type: str = None, level: str = None, limit: int = 1000):
    """Download filtered system logs as a text file."""
    _refresh_boot_sessions()
    filtered_logs = list(SYSTEM_LOGS)

    if type and type != "all":
        filtered_logs = [log for log in filtered_logs if log.get("type") == type]

    if level and level != "all":
        filtered_logs = [log for log in filtered_logs if log.get("level") == level]

    selected = filtered_logs[-limit:]

    def _format_log_line(log: dict) -> str:
        return (
            f"[{log.get('timestamp', '')}] "
            f"[{log.get('level', '')}] "
            f"[{log.get('type', '')}] "
            f"{log.get('message', '')}"
        )

    log_text = "\n".join(_format_log_line(log) for log in selected)
    if log_text:
        log_text += "\n"

    filename = f"ipxe-logs-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.txt"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return PlainTextResponse(content=log_text, headers=headers)


@monitoring_router.post("/logs/clear")
async def clear_logs():
    """Clear all system logs."""
    import app.routes.state as _state

    _state.SYSTEM_LOGS.clear()
    return {"success": True, "message": "Logs cleared"}


@monitoring_router.get("/boot-sessions")
async def get_boot_sessions():
    """Get active PXE boot sessions."""
    sessions = _refresh_boot_sessions()
    return {"success": True, "sessions": sessions, "count": len(sessions)}


@monitoring_router.get("/services")
async def get_service_status():
    """Get status of all services."""
    try:
        import subprocess

        tftp_status = "unknown"
        try:
            result = subprocess.run(
                ["service", "tftpd-hpa", "status"], capture_output=True, text=True, timeout=5
            )
            tftp_status = "running" if result.returncode == 0 else "stopped"
        except Exception:
            tftp_status = "unknown"

        rsyslog_status = "unknown"
        try:
            result = subprocess.run(
                ["service", "rsyslog", "status"], capture_output=True, text=True, timeout=5
            )
            rsyslog_status = "running" if result.returncode == 0 else "stopped"
        except Exception:
            rsyslog_status = "unknown"

        http_status = "running"
        http_port = int(os.getenv("UVICORN_PORT", "9021"))

        proxy_dhcp_manager = ProxyDHCPManager()
        proxy_dhcp_status = "running" if proxy_dhcp_manager.is_running() else "stopped"

        return {
            "success": True,
            "services": {
                "tftp": {"status": tftp_status, "uptime": 0},
                "http": {"status": http_status, "port": http_port},
                "rsyslog": {"status": rsyslog_status},
                "proxy_dhcp": {"status": proxy_dhcp_status},
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@monitoring_router.get("/metrics")
async def get_metrics():
    """Get system metrics."""
    try:
        import shutil

        stat = shutil.disk_usage(str(BASE_ROOT))

        with download_progress_lock:
            active_downloads = len(
                [k for k, v in download_progress.items() if v.get("status") == "downloading"]
            )

        return {
            "success": True,
            "metrics": {
                "disk_total": stat.total,
                "disk_used": stat.used,
                "disk_free": stat.free,
                "active_connections": active_downloads,
                "total_requests": 0,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

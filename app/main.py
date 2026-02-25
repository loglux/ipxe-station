import os
import shutil
import threading
import time
from pathlib import Path
from typing import List
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.backend.dhcp_helper import DHCPConfig, DHCPConfigGenerator, DHCPValidator
from app.backend.ipxe_manager import iPXEManager
from app.backend.ipxe_schema import IpxeMenuModel, menu_to_model, model_to_menu

app = FastAPI(title="iPXE Station", description="Network Boot Server")

# Global dictionary to track download progress (with thread safety)
download_progress = {}
download_progress_lock = threading.Lock()


# HTTP Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log HTTP requests to monitoring system."""
    # Skip logging for monitoring endpoints to avoid noise
    if not request.url.path.startswith("/api/monitoring"):
        from datetime import datetime

        start_time = datetime.now()

        response = await call_next(request)

        # Log significant requests (not static assets)
        if not request.url.path.startswith(("/ui/", "/status")):
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000

            # Determine log level based on status code
            level = "info"
            if response.status_code >= 400:
                level = "warning" if response.status_code < 500 else "error"

            # Log the request
            message = f"{request.method} {request.url.path} - {response.status_code} ({duration_ms:.0f}ms)"
            if request.client:
                message = f"{request.client.host} - {message}"

            add_log("http", level, message)

        return response
    else:
        return await call_next(request)


# In-memory log storage for monitoring
SYSTEM_LOGS = []
MAX_LOGS = 1000


def add_log(log_type: str, level: str, message: str):
    """Add a log entry to the system logs."""
    global SYSTEM_LOGS
    from datetime import datetime

    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": log_type,
        "level": level,
        "message": message,
    }

    SYSTEM_LOGS.append(log_entry)

    # Keep only last MAX_LOGS entries
    if len(SYSTEM_LOGS) > MAX_LOGS:
        SYSTEM_LOGS = SYSTEM_LOGS[-MAX_LOGS:]

    print(f"[{log_type}] [{level}] {message}")


# Base data root (fallback to /tmp/ipxe if /srv not writable)
BASE_ROOT = Path(os.getenv("IPXE_DATA_ROOT", "/srv"))
try:
    BASE_ROOT.mkdir(parents=True, exist_ok=True)
except PermissionError:
    BASE_ROOT = Path("/tmp/ipxe")
    BASE_ROOT.mkdir(parents=True, exist_ok=True)

HTTP_ROOT = BASE_ROOT / "http"
IPXE_ROOT = BASE_ROOT / "ipxe"
TFTP_ROOT = BASE_ROOT / "tftp"

for d in (HTTP_ROOT, IPXE_ROOT, TFTP_ROOT):
    d.mkdir(parents=True, exist_ok=True)


def _resolve_within_root(
    root: Path,
    raw_path: str,
    *,
    allow_empty: bool = False,
    fallback_name: str = "",
    path_label: str = "path",
) -> Path:
    """Resolve a user-supplied path and ensure it stays inside root."""
    value = (raw_path or "").strip()

    if not value:
        if fallback_name:
            value = fallback_name
        elif allow_empty:
            return root.resolve()
        else:
            raise HTTPException(status_code=400, detail=f"Missing {path_label}")

    candidate = Path(value)
    if candidate.is_absolute():
        raise HTTPException(
            status_code=400, detail=f"Invalid {path_label}: absolute paths are not allowed"
        )

    resolved = (root / candidate).resolve()
    root_resolved = root.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid {path_label}: path escapes root directory"
        )

    return resolved


def _validate_filename(filename: str) -> str:
    """Validate uploaded filename and reject traversal attempts."""
    value = (filename or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="Invalid filename: empty filename")

    name = Path(value).name
    if value != name or name in {".", ".."}:
        raise HTTPException(
            status_code=400, detail="Invalid filename: nested paths are not allowed"
        )

    return name


# Mount static file serving for HTTP boot
app.mount("/http", StaticFiles(directory=str(HTTP_ROOT)), name="http")


# Mount iPXE files
@app.get("/ipxe/{filename}")
@app.head("/ipxe/{filename}")
async def serve_ipxe(filename: str):
    """Serve iPXE files"""
    try:
        # Construct and resolve path
        file_path = (IPXE_ROOT / filename).resolve()
        ipxe_root_resolved = IPXE_ROOT.resolve()

        # Validate path is within IPXE_ROOT (prevent directory traversal)
        file_path.relative_to(ipxe_root_resolved)

        if file_path.exists():
            return FileResponse(
                file_path, media_type="text/plain", headers={"Cache-Control": "no-cache"}
            )
    except (ValueError, OSError):
        # Path traversal attempt or invalid path
        pass

    return Response("File not found", status_code=404)


# Mount TFTP files (for HTTP access if needed)
@app.get("/tftp/{filename}")
async def serve_tftp(filename: str):
    """Serve TFTP files via HTTP"""
    try:
        # Construct and resolve path
        file_path = (TFTP_ROOT / filename).resolve()
        tftp_root_resolved = TFTP_ROOT.resolve()

        # Validate path is within TFTP_ROOT (prevent directory traversal)
        file_path.relative_to(tftp_root_resolved)

        if file_path.exists():
            return FileResponse(file_path)
    except (ValueError, OSError):
        # Path traversal attempt or invalid path
        pass

    return Response("File not found", status_code=404)


@app.get("/")
async def root():
    """Redirect to React UI"""
    return RedirectResponse(url="/ui")


@app.get("/status")
async def status():
    """Server status"""
    return {
        "tftp_files": len(list(TFTP_ROOT.glob("*"))),
        "http_files": len(list(HTTP_ROOT.rglob("*"))),
        "ipxe_files": len(list(IPXE_ROOT.glob("*"))),
    }


def _list_relative_files(base: Path, max_depth: int = 2) -> List[str]:
    """Return relative file paths up to max_depth levels."""
    files: List[str] = []
    base_depth = len(base.parts)
    for path in base.rglob("*"):
        if path.is_file():
            depth = len(path.parts) - base_depth
            if depth <= max_depth:
                files.append(str(path.relative_to(base)))
    return sorted(files)


def _scan_distro_versions(prefix: str, base: Path):
    """Scan for distro directories like ubuntu-22.04 containing kernel/initrd/iso."""
    results = []
    for path in base.glob(f"{prefix}-*"):
        if not path.is_dir():
            continue
        version = path.name.replace(f"{prefix}-", "")
        kernel = None
        initrd = None
        iso = None
        wim = None

        # Kaspersky-specific file names
        if prefix == "kaspersky":
            # Version 24 uses vmlinuz, version 18 uses k-x86_64
            for name in ["vmlinuz", "k-x86_64", "k-x86"]:
                candidate = path / name
                if candidate.exists():
                    kernel = f"{path.name}/{name}"
                    break
            # Version 24 uses initrd.img, version 18 uses initrd.xz
            for name in ["initrd.img", "initrd.xz", "initrd"]:
                candidate = path / name
                if candidate.exists():
                    initrd = f"{path.name}/{name}"
                    break
        else:
            # Common kernel names for other distros
            for name in ["vmlinuz", "linux"]:
                candidate = path / name
                if candidate.exists():
                    kernel = f"{path.name}/{name}"
                    break
            # Common initrd names
            for name in ["initrd", "initrd.img", "initrd.lz", "initrd.xz"]:
                candidate = path / name
                if candidate.exists():
                    initrd = f"{path.name}/{name}"
                    break

        # ISO and WIM files (common for all)
        for item in path.glob("*.iso"):
            iso = f"{path.name}/{item.name}"
            break
        for item in path.glob("*.wim"):
            wim = f"{path.name}/{item.name}"
            break

        results.append(
            {"version": version, "kernel": kernel, "initrd": initrd, "iso": iso, "wim": wim}
        )
    return results


# API: iPXE config validation/generation
ipxe_router = APIRouter(prefix="/api/ipxe", tags=["ipxe"])
ipxe_manager = iPXEManager(config_path=IPXE_ROOT / "boot.ipxe")


def _default_menu_structure() -> dict:
    """Return backend-owned starter menu structure."""
    settings = load_settings()
    return {
        "title": "PXE Boot Menu",
        "timeout": settings.default_timeout,
        "default_entry": None,
        "entries": [
            {
                "name": "linux",
                "title": "Linux",
                "entry_type": "submenu",
                "enabled": True,
                "order": 1,
                "parent": None,
            },
            {
                "name": "windows",
                "title": "Windows",
                "entry_type": "submenu",
                "enabled": True,
                "order": 2,
                "parent": None,
            },
            {
                "name": "tools",
                "title": "Rescue & Tools",
                "entry_type": "submenu",
                "enabled": True,
                "order": 3,
                "parent": None,
            },
        ],
        "header_text": "",
        "footer_text": "",
        "server_ip": settings.server_ip,
        "http_port": settings.http_port,
    }


def _apply_runtime_network_defaults(menu: IpxeMenuModel) -> IpxeMenuModel:
    """Apply backend settings when client did not provide explicit network values."""
    settings = load_settings()
    updates = {}

    if menu.server_ip in {"", "localhost", "127.0.0.1"}:
        updates["server_ip"] = settings.server_ip

    if menu.http_port in {0, 8000}:
        updates["http_port"] = settings.http_port

    return menu.model_copy(update=updates) if updates else menu


@ipxe_router.get("/menu/default")
def get_default_menu():
    """Return backend-defined starter menu for thin clients."""
    return {"success": True, "menu": _default_menu_structure(), "source": "default"}


@ipxe_router.post("/validate")
def validate_ipxe(menu: IpxeMenuModel):
    menu = _apply_runtime_network_defaults(menu)
    menu_dc = model_to_menu(menu)
    is_valid, errors = ipxe_manager.validator.validate_menu(menu_dc)
    warnings = ipxe_manager.validator.lint_menu(menu_dc)
    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
    }


@ipxe_router.post("/generate")
def generate_ipxe(menu: IpxeMenuModel):
    menu = _apply_runtime_network_defaults(menu)
    menu_dc = model_to_menu(menu)
    is_valid, message, script_content = ipxe_manager.validate_and_generate(menu_dc)
    warnings = ipxe_manager.validator.lint_menu(menu_dc)
    return {
        "valid": is_valid,
        "message": message,
        "warnings": warnings,
        "script": script_content if is_valid else "",
    }


@ipxe_router.get("/templates")
def list_templates():
    return {"templates": ["ubuntu", "ubuntu_multi", "ubuntu_quick", "diagnostic", "multi_os"]}


@ipxe_router.post("/templates/{template_name}")
def get_template(template_name: str, server_ip: str = "localhost", port: int = 8000):
    menu = ipxe_manager.get_template(template_name, server_ip=server_ip, port=port)
    if not menu:
        return Response("Template not found", status_code=404)
    model = menu_to_model(menu)
    return model.model_dump()


@ipxe_router.get("/menu/load")
def load_current_menu():
    """Load the current boot.ipxe file content."""
    ok, message, content = ipxe_manager.load_menu_from_file()
    return {
        "success": ok,
        "message": message,
        "script": content if ok else "",
        "config_path": str(ipxe_manager.config_path),
    }


def _parse_boot_ipxe(script_content: str) -> dict:
    """Parse boot.ipxe script and extract menu structure."""
    import re

    entries = []
    lines = script_content.split("\n")

    # Extract menu items from :start section
    in_start_menu = False
    in_submenu = None
    current_submenu_items = []

    # First pass: extract menu items
    for line in lines:
        line = line.strip()

        if line == ":start":
            in_start_menu = True
            continue
        elif line.startswith(":submenu_"):
            in_submenu = line[1:]  # Remove ':' prefix
            current_submenu_items = []
            continue
        elif line.startswith(":") and in_start_menu:
            in_start_menu = False
        elif line.startswith(":") and in_submenu:
            in_submenu = None

        # Parse menu item lines
        if line.startswith("item ") and not line.startswith("item --gap"):
            parts = line.split(None, 2)  # Split into max 3 parts
            if len(parts) >= 3:
                name = parts[1]
                title = parts[2]

                # Check if it's a submenu (ends with -->)
                is_submenu = title.endswith("-->")
                if is_submenu:
                    title = title[:-3].strip()

                # Determine entry type
                if is_submenu:
                    entry_type = "submenu"
                elif name.startswith("back_") or name in ["shell", "reboot", "exit"]:
                    entry_type = "action"
                else:
                    entry_type = "boot"

                entry = {
                    "name": name,
                    "title": title,
                    "entry_type": entry_type,
                    "enabled": True,
                    "order": len(entries),
                    "parent": in_submenu.replace("submenu_", "") if in_submenu else None,
                }
                entries.append(entry)

    # Second pass: extract boot configurations
    current_label = None
    for i, line in enumerate(lines):
        line = line.strip()

        if (
            line.startswith(":")
            and not line.startswith(":start")
            and not line.startswith(":submenu")
        ):
            current_label = line[1:]  # Remove ':'

            # Find matching entry
            for entry in entries:
                if entry["name"] == current_label and entry["entry_type"] == "boot":
                    # Look ahead for kernel, initrd, imgargs
                    for j in range(i + 1, min(i + 20, len(lines))):
                        next_line = lines[j].strip()

                        if next_line.startswith("kernel "):
                            parts = next_line.split(None, 1)
                            if len(parts) >= 2:
                                entry["kernel"] = parts[1].split()[0] if parts[1] else ""
                        elif next_line.startswith("initrd "):
                            parts = next_line.split(None, 1)
                            if len(parts) >= 2:
                                entry["initrd"] = parts[1].strip()
                        elif next_line.startswith("imgargs "):
                            # Extract cmdline from imgargs (with validation)
                            try:
                                cmdline_match = re.search(r"imgargs\s+\w+\s+(.+)", next_line)
                                if cmdline_match:
                                    # Remove --- separator and strip whitespace
                                    entry["cmdline"] = (
                                        cmdline_match.group(1).replace(" ---", "").strip()
                                    )
                            except (IndexError, AttributeError):
                                # Malformed imgargs line, skip it
                                pass
                        elif next_line.startswith("boot"):
                            break
                        elif next_line.startswith(":"):
                            break

                    # Set defaults for missing fields
                    entry.setdefault("kernel", "")
                    entry.setdefault("initrd", "")
                    entry.setdefault("cmdline", "")
                    entry.setdefault("description", "")
                    entry.setdefault("url", "")
                    entry.setdefault("boot_mode", "netboot")
                    entry.setdefault("requires_iso", False)
                    entry.setdefault("requires_internet", False)

    settings = load_settings()
    return {
        "title": "PXE Boot Menu",
        "timeout": settings.default_timeout,
        "entries": entries,
        "header_text": "",
        "footer_text": "",
        "server_ip": settings.server_ip,
        "http_port": settings.http_port,
    }


@ipxe_router.get("/menu/structure")
def load_menu_structure():
    """Load the saved menu structure (menu.json) or parse from boot.ipxe."""
    import json

    menu_json_path = IPXE_ROOT / "menu.json"
    boot_ipxe_path = IPXE_ROOT / "boot.ipxe"

    # Try to load menu.json first
    if menu_json_path.exists():
        try:
            with open(menu_json_path, "r") as f:
                menu_data = json.load(f)
            return {
                "success": True,
                "message": "Menu structure loaded from menu.json",
                "menu": menu_data,
                "source": "json",
            }
        except Exception as e:
            # Log error and fall through to boot.ipxe parsing
            add_log(
                "system",
                "warning",
                f"Failed to parse menu.json, falling back to boot.ipxe: {str(e)}",
            )

    # If menu.json doesn't exist, try to parse boot.ipxe
    if boot_ipxe_path.exists():
        try:
            with open(boot_ipxe_path, "r") as f:
                script_content = f.read()

            menu_data = _parse_boot_ipxe(script_content)

            # Save parsed structure as menu.json for future use
            try:
                with open(menu_json_path, "w") as f:
                    json.dump(menu_data, f, indent=2)
            except Exception as e:
                # Log the error but don't fail the parsing operation
                add_log("system", "warning", f"Failed to save menu.json: {str(e)}")

            return {
                "success": True,
                "message": "Menu structure parsed from boot.ipxe",
                "menu": menu_data,
                "source": "parsed",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to parse boot.ipxe: {str(e)}",
                "menu": None,
            }

    # No files found
    return {"success": False, "message": "No saved menu structure found", "menu": None}


@ipxe_router.delete("/menu")
def delete_menu():
    """Delete both boot.ipxe and menu.json files."""
    import os

    boot_ipxe = IPXE_ROOT / "boot.ipxe"
    menu_json = IPXE_ROOT / "menu.json"

    deleted = []
    errors = []

    if boot_ipxe.exists():
        try:
            os.remove(boot_ipxe)
            deleted.append("boot.ipxe")
        except Exception as e:
            errors.append(f"boot.ipxe: {str(e)}")

    if menu_json.exists():
        try:
            os.remove(menu_json)
            deleted.append("menu.json")
        except Exception as e:
            errors.append(f"menu.json: {str(e)}")

    return {
        "success": len(errors) == 0,
        "message": f"Deleted: {', '.join(deleted)}" if deleted else "No files to delete",
        "deleted": deleted,
        "errors": errors,
    }


@ipxe_router.post("/menu/save")
def save_menu(menu: IpxeMenuModel):
    import json

    menu = _apply_runtime_network_defaults(menu)
    menu_dc = model_to_menu(menu)
    is_valid, message, script_content = ipxe_manager.validate_and_generate(menu_dc)
    warnings = ipxe_manager.validator.lint_menu(menu_dc)
    if not is_valid:
        return {
            "valid": False,
            "message": message,
            "warnings": warnings,
            "script": "",
        }

    # Save the iPXE script
    ok, save_msg = ipxe_manager.save_menu(menu_dc)

    # Also save the menu structure as JSON for future editing
    if ok:
        add_log("system", "info", f"Menu saved successfully: {len(menu.entries)} entries")
        menu_json_path = IPXE_ROOT / "menu.json"
        try:
            with open(menu_json_path, "w") as f:
                json.dump(menu.model_dump(), f, indent=2)
        except Exception as e:
            # Don't fail if JSON save fails, just log it
            save_msg += f" (Warning: Failed to save menu.json: {str(e)})"
            add_log("system", "warning", f"Failed to save menu.json: {str(e)}")
    else:
        add_log("system", "error", f"Menu save failed: {message}")

    return {
        "valid": ok,
        "message": save_msg if ok else message,
        "warnings": warnings,
        "script": script_content if ok else "",
        "config_path": str(ipxe_manager.config_path),
    }


app.include_router(ipxe_router)


# ==============================================================================
# BOOT FILES MANAGEMENT
# ==============================================================================

boot_router = APIRouter(prefix="/api/boot", tags=["boot"])

# Templates for autoexec.ipxe
AUTOEXEC_TEMPLATES = {
    "direct": {
        "name": "Direct Boot (HTTP with TFTP fallback)",
        "description": "Fastest - loads boot menu directly via HTTP with TFTP fallback",
        "content": """#!ipxe
dhcp || echo DHCP failed, trying static config...
echo Loading PXE boot menu...
chain http://${next-server}:${http-port}/ipxe/boot.ipxe || chain tftp://${next-server}/boot.ipxe
""",
    },
    "chainload": {
        "name": "Chainload Full iPXE",
        "description": "For limited PXE ROMs - loads full-featured iPXE first",
        "content": """#!ipxe
dhcp || echo DHCP failed...
echo Loading full iPXE...
chain tftp://${next-server}/undionly.kpxe || chain tftp://${next-server}/ipxe.efi
""",
    },
    "custom": {
        "name": "Custom Script",
        "description": "Write your own iPXE script",
        "content": """#!ipxe
# Custom iPXE script
# Available variables: ${next-server}, ${http-port}

dhcp

# Your code here
""",
    },
}


@boot_router.get("/autoexec")
def get_autoexec():
    """Get current autoexec.ipxe content."""
    autoexec_path = TFTP_ROOT / "autoexec.ipxe"

    if not autoexec_path.exists():
        return {"exists": False, "content": "", "message": "autoexec.ipxe not found"}

    try:
        with open(autoexec_path, "r") as f:
            content = f.read()

        return {"exists": True, "content": content, "path": str(autoexec_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read autoexec.ipxe: {str(e)}")


@boot_router.post("/autoexec")
def save_autoexec(payload: "AutoexecSaveRequest"):
    """Save autoexec.ipxe content."""
    autoexec_path = TFTP_ROOT / "autoexec.ipxe"

    try:
        content = payload.content

        # Save file
        with open(autoexec_path, "w") as f:
            f.write(content)

        # Set executable permission
        os.chmod(autoexec_path, 0o755)

        add_log("system", "info", f"autoexec.ipxe saved ({len(content)} bytes)")

        return {
            "success": True,
            "message": "autoexec.ipxe saved successfully",
            "path": str(autoexec_path),
            "size": len(content),
        }
    except Exception as e:
        add_log("system", "error", f"Failed to save autoexec.ipxe: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save autoexec.ipxe: {str(e)}")


class AutoexecTemplateRequest(BaseModel):
    template: str
    next_server: str = os.getenv("PXE_SERVER_IP", "192.168.1.1")  # Default to common router IP
    http_port: int = 9021


class AutoexecSaveRequest(BaseModel):
    content: str = ""


@boot_router.post("/autoexec/apply-template")
def apply_autoexec_template(request: AutoexecTemplateRequest):
    """Apply a template to autoexec.ipxe with variable substitution."""

    if request.template not in AUTOEXEC_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown template: {request.template}")

    template = AUTOEXEC_TEMPLATES[request.template]
    content = template["content"]

    # Substitute variables
    content = content.replace("${next-server}", request.next_server)
    content = content.replace("${http-port}", str(request.http_port))

    autoexec_path = TFTP_ROOT / "autoexec.ipxe"

    try:
        with open(autoexec_path, "w") as f:
            f.write(content)

        os.chmod(autoexec_path, 0o755)

        add_log("system", "info", f"Applied template '{template['name']}' to autoexec.ipxe")

        return {
            "success": True,
            "message": f"Applied template: {template['name']}",
            "content": content,
            "template": request.template,
        }
    except Exception as e:
        add_log("system", "error", f"Failed to apply template: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to apply template: {str(e)}")


@boot_router.get("/autoexec/templates")
def get_autoexec_templates():
    """Get available autoexec.ipxe templates."""
    return {
        "templates": {
            key: {"name": tpl["name"], "description": tpl["description"]}
            for key, tpl in AUTOEXEC_TEMPLATES.items()
        }
    }


@boot_router.get("/files")
def get_boot_files():
    """Get list of boot files in TFTP root."""
    try:
        boot_files = []

        for file_path in TFTP_ROOT.glob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                boot_files.append(
                    {
                        "name": file_path.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "executable": os.access(file_path, os.X_OK),
                    }
                )

        return {"files": boot_files, "path": str(TFTP_ROOT)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list boot files: {str(e)}")


app.include_router(boot_router)


@app.get("/api/assets")
def list_assets():
    """List available boot assets in http/tftp/ipxe roots (shallow)."""
    return {
        "http": _list_relative_files(HTTP_ROOT, max_depth=3),
        "tftp": _list_relative_files(TFTP_ROOT, max_depth=3),
        "ipxe": _list_relative_files(IPXE_ROOT, max_depth=3),
    }


@app.get("/api/assets/catalog")
def assets_catalog():
    """Return discovered distro assets by version."""
    ubuntu = _scan_distro_versions("ubuntu", HTTP_ROOT)
    debian = _scan_distro_versions("debian", HTTP_ROOT)
    windows = _scan_distro_versions("windows", HTTP_ROOT)
    rescue = _scan_distro_versions("rescue", HTTP_ROOT)
    kaspersky = _scan_distro_versions("kaspersky", HTTP_ROOT)

    # Keep rescue and kaspersky separate to avoid confusion in the wizard
    return {
        "ubuntu": ubuntu,
        "debian": debian,
        "windows": windows,
        "rescue": rescue,
        "kaspersky": kaspersky,
    }


class DownloadRequest(BaseModel):
    url: str
    dest: str = ""


@app.post("/api/assets/download")
def download_asset(request: DownloadRequest):
    """Download a remote asset into /srv/http/<dest> (relative) with progress tracking."""
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Only http/https URLs allowed")

    default_filename = Path(urlparse(request.url).path).name or "download.bin"
    target = _resolve_within_root(
        HTTP_ROOT,
        request.dest,
        fallback_name=default_filename,
        path_label="dest",
    )
    target.parent.mkdir(parents=True, exist_ok=True)

    # Create progress tracking key
    progress_key = str(target.relative_to(HTTP_ROOT.resolve()))

    try:
        # Timeout: (connect=30s, read=600s) to handle large ISO downloads
        with requests.get(request.url, stream=True, timeout=(30, 600)) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))

            # Initialize progress tracking
            with download_progress_lock:
                download_progress[progress_key] = {
                    "downloaded": 0,
                    "total": total_size,
                    "percentage": 0,
                    "status": "downloading",
                }

            # Log download start
            add_log("download", "info", f"Started downloading {progress_key} ({total_size} bytes)")

            downloaded = 0
            with open(target, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
                        downloaded += len(chunk)

                        # Update progress every MB or so
                        if downloaded % (1024 * 1024) < 8192 or downloaded == total_size:
                            percentage = (downloaded / total_size * 100) if total_size > 0 else 0
                            with download_progress_lock:
                                download_progress[progress_key] = {
                                    "downloaded": downloaded,
                                    "total": total_size,
                                    "percentage": round(percentage, 1),
                                    "status": "downloading",
                                }

            # Mark download as complete
            with download_progress_lock:
                download_progress[progress_key] = {
                    "downloaded": downloaded,
                    "total": total_size,
                    "percentage": 100,
                    "status": "complete",
                }

            # Log download completion
            add_log(
                "download", "info", f"Completed downloading {progress_key} ({downloaded} bytes)"
            )

            # Auto-extract ISO files
            if target.suffix.lower() == ".iso":
                with download_progress_lock:
                    download_progress[progress_key]["status"] = "extracting"
                add_log("download", "info", f"Starting ISO extraction for {progress_key}")

                # Determine extraction directory (same as ISO parent folder)
                extract_dir = target.parent

                # Perform full ISO extraction
                extraction_result = _extract_full_iso(target, extract_dir)

                if extraction_result["success"]:
                    with download_progress_lock:
                        download_progress[progress_key]["status"] = "extracted"
                        download_progress[progress_key]["file_count"] = extraction_result.get(
                            "file_count", 0
                        )
                    add_log(
                        "download",
                        "info",
                        f"Extracted {extraction_result.get('file_count', 0)} files from {progress_key}",
                    )
                else:
                    with download_progress_lock:
                        download_progress[progress_key]["status"] = "extraction_failed"
                        download_progress[progress_key]["extraction_error"] = extraction_result.get(
                            "error", "Unknown error"
                        )
                    add_log(
                        "download",
                        "error",
                        f"ISO extraction failed for {progress_key}: {extraction_result.get('error', 'Unknown error')}",
                    )

    except Exception as exc:
        with download_progress_lock:
            download_progress[progress_key] = {
                "downloaded": 0,
                "total": 0,
                "percentage": 0,
                "status": "error",
                "error": str(exc),
            }
        add_log("download", "error", f"Download failed for {progress_key}: {str(exc)}")
        raise HTTPException(status_code=500, detail=f"Download failed: {exc}")

    return {"saved": str(target.relative_to(HTTP_ROOT))}


@app.get("/api/assets/download/progress/{file_path:path}")
def get_download_progress(file_path: str):
    """Get download progress for a specific file."""
    with download_progress_lock:
        if file_path in download_progress:
            return download_progress[file_path].copy()
        else:
            return {"status": "not_found"}


@app.get("/api/assets/download/progress")
def get_all_download_progress():
    """Get all active download progress."""
    with download_progress_lock:
        return {"downloads": download_progress.copy()}


@app.post("/api/assets/upload")
async def upload_asset(file: UploadFile = File(...), dest: str = ""):
    """Upload a file into /srv/http/<dest> (relative)."""
    target_dir = _resolve_within_root(HTTP_ROOT, dest, allow_empty=True, path_label="dest")
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = _validate_filename(file.filename)
    target_path = _resolve_within_root(target_dir, safe_filename, path_label="filename")
    try:
        with open(target_path, "wb") as fh:
            content = await file.read()
            fh.write(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")
    return {"saved": str(target_path.relative_to(HTTP_ROOT))}


class ExtractISORequest(BaseModel):
    iso_path: str
    kernel_path: str = ""
    initrd_path: str = ""
    dest_dir: str = ""
    kernel_filename: str = "vmlinuz"
    initrd_filename: str = "initrd"


def _extract_full_iso(iso_path: Path, dest_dir: Path) -> dict:
    """Helper function to extract entire ISO contents to destination directory."""
    import subprocess

    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Full extraction with directory structure preserved
        extract_cmd = ["7z", "x", str(iso_path), f"-o{dest_dir}", "-y"]
        result = subprocess.run(extract_cmd, check=True, capture_output=True, text=True)

        # Count extracted files
        file_count = sum(1 for _ in dest_dir.rglob("*") if _.is_file())

        return {"success": True, "dest_dir": str(dest_dir), "file_count": file_count}
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Extraction failed: {e.stderr if e.stderr else str(e)}",
        }
    except Exception as exc:
        return {"success": False, "error": f"Extraction failed: {exc}"}


@app.post("/api/assets/extract-iso")
def extract_iso(request: ExtractISORequest):
    """Extract kernel and initrd from an ISO file using 7zip."""
    import subprocess

    # Resolve ISO path (relative to HTTP_ROOT)
    iso_file = _resolve_within_root(HTTP_ROOT, request.iso_path, path_label="iso_path")
    if not iso_file.exists():
        raise HTTPException(status_code=404, detail=f"ISO file not found: {request.iso_path}")

    # Determine destination directory
    if request.dest_dir:
        dest_dir = _resolve_within_root(HTTP_ROOT, request.dest_dir, path_label="dest_dir")
    else:
        dest_dir = _resolve_within_root(
            HTTP_ROOT, str(iso_file.relative_to(HTTP_ROOT.resolve()).parent / iso_file.stem)
        )
    dest_dir.mkdir(parents=True, exist_ok=True)

    kernel_filename = _validate_filename(request.kernel_filename)
    initrd_filename = _validate_filename(request.initrd_filename)

    try:
        # List contents of ISO to find kernel and initrd
        list_cmd = ["7z", "l", str(iso_file)]
        result = subprocess.run(list_cmd, capture_output=True, text=True, check=True)
        iso_contents = result.stdout

        # Auto-detect paths if not provided
        kernel_in_iso = request.kernel_path
        initrd_in_iso = request.initrd_path

        if not kernel_in_iso or not initrd_in_iso:
            # Try to find common paths
            lines = iso_contents.split("\n")
            for line in lines:
                if not kernel_in_iso and any(
                    x in line.lower() for x in ["vmlinuz", "linux", "kernel"]
                ):
                    # Extract path from 7z output
                    parts = line.split()
                    if len(parts) >= 6:
                        potential_path = " ".join(parts[5:])
                        if "vmlinuz" in potential_path or "linux" in potential_path:
                            kernel_in_iso = potential_path

                if not initrd_in_iso and any(
                    x in line.lower() for x in ["initrd", "initramfs", "sysresccd.img"]
                ):
                    parts = line.split()
                    if len(parts) >= 6:
                        potential_path = " ".join(parts[5:])
                        if any(
                            x in potential_path.lower()
                            for x in ["initrd", "initramfs", "sysresccd.img"]
                        ):
                            initrd_in_iso = potential_path

        extracted_files = {}

        # Extract kernel
        if kernel_in_iso:
            extract_cmd = ["7z", "e", str(iso_file), f"-o{dest_dir}", kernel_in_iso, "-y"]
            subprocess.run(extract_cmd, check=True, capture_output=True)

            # Rename if necessary
            extracted_name = Path(kernel_in_iso).name
            source_file = dest_dir / extracted_name
            target_file = dest_dir / kernel_filename

            if source_file.exists() and source_file != target_file:
                source_file.rename(target_file)
                extracted_files["kernel"] = str(target_file.relative_to(HTTP_ROOT))
            elif target_file.exists():
                extracted_files["kernel"] = str(target_file.relative_to(HTTP_ROOT))

        # Extract initrd
        if initrd_in_iso:
            extract_cmd = ["7z", "e", str(iso_file), f"-o{dest_dir}", initrd_in_iso, "-y"]
            subprocess.run(extract_cmd, check=True, capture_output=True)

            # Rename if necessary
            extracted_name = Path(initrd_in_iso).name
            source_file = dest_dir / extracted_name
            target_file = dest_dir / initrd_filename

            if source_file.exists() and source_file != target_file:
                source_file.rename(target_file)
                extracted_files["initrd"] = str(target_file.relative_to(HTTP_ROOT))
            elif target_file.exists():
                extracted_files["initrd"] = str(target_file.relative_to(HTTP_ROOT))

        # Create symlink to original ISO in dest directory
        iso_link = dest_dir / iso_file.name
        if not iso_link.exists():
            iso_link.symlink_to(iso_file)
            extracted_files["iso"] = str(iso_link.relative_to(HTTP_ROOT))

        return {
            "success": True,
            "dest_dir": str(dest_dir.relative_to(HTTP_ROOT)),
            "extracted_files": extracted_files,
            "kernel_path": kernel_in_iso,
            "initrd_path": initrd_in_iso,
        }

    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500, detail=f"Extraction failed: {e.stderr if e.stderr else str(e)}"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")


@app.get("/api/assets/versions/systemrescue")
def get_systemrescue_versions():
    """Fetch available SystemRescue versions from SourceForge."""
    try:
        import re

        from bs4 import BeautifulSoup

        url = "https://sourceforge.net/projects/systemrescuecd/files/sysresccd-x86/"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        versions_dict = {}  # Use dict to deduplicate by version number

        # Find all version folders (format: X.Y.Z/)
        for link in soup.find_all("a", href=True):
            href = link["href"]
            # Match version pattern like /projects/systemrescuecd/files/sysresccd-x86/11.02/
            match = re.search(r"/sysresccd-x86/(\d+\.\d+(?:\.\d+)?)", href)
            if match:
                version = match.group(1)
                if version not in versions_dict:  # Deduplicate
                    # Construct direct download URL
                    iso_name = f"systemrescue-{version}-amd64.iso"
                    download_url = f"https://sourceforge.net/projects/systemrescuecd/files/sysresccd-x86/{version}/{iso_name}/download"

                    versions_dict[version] = {
                        "version": version,
                        "name": f"SystemRescue {version}",
                        "iso_url": download_url,
                        "iso_name": iso_name,
                        "size_est": "~950 MB",
                    }

        # Convert to list and sort by version (newest first)
        versions = list(versions_dict.values())
        versions.sort(key=lambda x: [int(n) for n in x["version"].split(".")], reverse=True)
        return {"versions": versions[:10]}  # Return top 10 versions

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch versions: {exc}")


@app.get("/api/assets/versions/kaspersky")
def get_kaspersky_versions():
    """Return available Kaspersky Rescue Disk versions."""
    versions = [
        {
            "version": "24",
            "name": "Kaspersky Rescue Disk 24 (Recommended)",
            "iso_url": "https://rescuedisk.s.kaspersky-labs.com/updatable/2024/krd.iso",
            "iso_name": "krd-24.iso",
            "size_est": "~800 MB",
            "notes": "Better UEFI support, requires 2.5GB+ RAM",
        },
        {
            "version": "18",
            "name": "Kaspersky Rescue Disk 18",
            "iso_url": "https://rescuedisk.s.kaspersky-labs.com/krd.iso",
            "iso_name": "krd-18.iso",
            "size_est": "~670 MB",
            "notes": "UEFI Secure Boot NOT supported",
        },
    ]
    return {"versions": versions}


# Settings management
class SettingsModel(BaseModel):
    server_ip: str = os.getenv("PXE_SERVER_IP", "192.168.1.1")  # Default to common router IP
    http_port: int = 9021
    tftp_port: int = 69
    default_timeout: int = 30000  # milliseconds
    default_entry: str = ""
    auto_extraction: bool = True
    poll_interval: int = 2000  # milliseconds
    theme: str = "light"
    show_file_sizes: bool = True
    show_timestamps: bool = True


SETTINGS_FILE = IPXE_ROOT / "settings.json"


def load_settings() -> SettingsModel:
    """Load settings from file or return defaults."""
    if SETTINGS_FILE.exists():
        import json

        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                return SettingsModel(**data)
        except Exception as e:
            # Log error but return defaults to avoid breaking startup
            add_log("system", "warning", f"Failed to load settings from {SETTINGS_FILE}: {str(e)}")
    return SettingsModel()


def save_settings(settings: SettingsModel):
    """Save settings to file."""
    import json

    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings.model_dump(), f, indent=2)


@app.get("/api/settings")
def get_settings():
    """Get current settings."""
    return load_settings().model_dump()


@app.post("/api/settings")
def update_settings(settings: SettingsModel):
    """Update and save settings."""
    save_settings(settings)
    return {"success": True, "settings": settings.model_dump()}


@app.get("/api/network/detect")
def detect_network():
    """Auto-detect server IP address."""
    import socket

    try:
        # Create a socket to detect the primary network interface IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()

        # Also get all network interfaces
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


# API: DHCP Configuration Helper
dhcp_router = APIRouter(prefix="/api/dhcp", tags=["dhcp"])
dhcp_generator = DHCPConfigGenerator()
dhcp_validator = DHCPValidator()


@dhcp_router.get("/server-types")
def list_dhcp_server_types():
    """List supported DHCP server types"""
    return {"server_types": dhcp_generator.list_server_types()}


@dhcp_router.post("/config/generate")
def generate_dhcp_config(
    server_type: str = "dnsmasq",
    pxe_server_ip: str = "192.168.10.32",
    http_port: int = 9021,
    tftp_port: int = 69,
):
    """Generate DHCP configuration for specified server type"""
    try:
        config = DHCPConfig(
            pxe_server_ip=pxe_server_ip,
            http_port=http_port,
            tftp_port=tftp_port,
            server_type=server_type,
        )
        result = dhcp_generator.generate(config)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@dhcp_router.get("/validate/network")
def validate_network_dhcp():
    """Check and validate DHCP configuration on the network"""
    result = dhcp_validator.check_network()
    return result


app.include_router(dhcp_router)


# ==============================================================================
# MONITORING ENDPOINTS
# ==============================================================================


@app.get("/api/monitoring/logs")
async def get_logs(type: str = None, level: str = None, limit: int = 100):
    """Get system logs with optional filtering."""
    try:
        filtered_logs = SYSTEM_LOGS.copy()

        # Filter by type
        if type and type != "all":
            filtered_logs = [log for log in filtered_logs if log.get("type") == type]

        # Filter by level
        if level and level != "all":
            filtered_logs = [log for log in filtered_logs if log.get("level") == level]

        # Limit results
        filtered_logs = filtered_logs[-limit:]

        return {"success": True, "logs": filtered_logs}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/monitoring/logs/clear")
async def clear_logs():
    """Clear all system logs."""
    global SYSTEM_LOGS
    SYSTEM_LOGS = []
    return {"success": True, "message": "Logs cleared"}


@app.get("/api/monitoring/services")
async def get_service_status():
    """Get status of all services."""
    try:
        import subprocess

        # Check TFTP service
        tftp_status = "unknown"
        try:
            result = subprocess.run(
                ["service", "tftpd-hpa", "status"], capture_output=True, text=True, timeout=5
            )
            tftp_status = "running" if result.returncode == 0 else "stopped"
        except:
            tftp_status = "unknown"

        # Check rsyslog service
        rsyslog_status = "unknown"
        try:
            result = subprocess.run(
                ["service", "rsyslog", "status"], capture_output=True, text=True, timeout=5
            )
            rsyslog_status = "running" if result.returncode == 0 else "stopped"
        except:
            rsyslog_status = "unknown"

        # HTTP server is always running if this endpoint responds
        http_status = "running"
        http_port = int(os.getenv("UVICORN_PORT", "9021"))

        return {
            "success": True,
            "services": {
                "tftp": {"status": tftp_status, "uptime": 0},
                "http": {"status": http_status, "port": http_port},
                "rsyslog": {"status": rsyslog_status},
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/monitoring/metrics")
async def get_metrics():
    """Get system metrics."""
    try:
        import shutil

        # Disk usage
        stat = shutil.disk_usage(str(BASE_ROOT))
        disk_total = stat.total
        disk_used = stat.used
        disk_free = stat.free

        # Count active downloads (with thread safety)
        with download_progress_lock:
            active_downloads = len(
                [k for k, v in download_progress.items() if v.get("status") == "downloading"]
            )

        # Total requests (we don't track this yet, placeholder)
        total_requests = 0

        return {
            "success": True,
            "metrics": {
                "disk_total": disk_total,
                "disk_used": disk_used,
                "disk_free": disk_free,
                "active_connections": active_downloads,
                "total_requests": total_requests,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==============================================================================
# SYSLOG INTEGRATION FOR TFTP LOGS
# ==============================================================================

# Track last read position in syslog
syslog_position = 0
syslog_monitor_running = False


def parse_syslog_tftp():
    """Parse syslog for TFTP entries and add to monitoring."""
    global syslog_position

    syslog_path = Path("/var/log/syslog")
    if not syslog_path.exists():
        return

    try:
        with open(syslog_path, "r") as f:
            # Seek to last position
            f.seek(syslog_position)

            for line in f:
                # Parse TFTP log lines
                if "in.tftpd" in line:
                    # Extract timestamp, IP, and message
                    parts = line.strip().split()
                    if len(parts) >= 6:
                        timestamp = " ".join(parts[0:2])
                        message = " ".join(parts[5:])

                        # Extract client IP if present
                        client_ip = "unknown"
                        if "RRQ from" in message:
                            try:
                                client_ip = message.split("RRQ from ")[1].split()[0]
                                filename = (
                                    message.split("filename ")[1]
                                    if "filename" in message
                                    else "unknown"
                                )
                                add_log(
                                    "tftp", "info", f"Download request from {client_ip}: {filename}"
                                )
                            except:
                                add_log("tftp", "info", message)
                        elif "tftp:" in message:
                            add_log("tftp", "warning", message)
                        else:
                            add_log("tftp", "debug", message)

            # Update position
            syslog_position = f.tell()
    except Exception as e:
        print(f"Error parsing syslog: {e}")


def syslog_monitor_thread():
    """Background thread to monitor syslog."""
    global syslog_monitor_running
    syslog_monitor_running = True

    while syslog_monitor_running:
        parse_syslog_tftp()
        time.sleep(2)  # Check every 2 seconds


# Start syslog monitor in background
monitor_thread = threading.Thread(target=syslog_monitor_thread, daemon=True)
monitor_thread.start()

# Add initial log entry
add_log("system", "info", "iPXE Station monitoring initialized")
add_log("system", "info", "TFTP log integration started")


# Serve built frontend (Vite)
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="ui")
else:
    print("Warning: Frontend dist directory not found. Build the frontend first.")

if __name__ == "__main__":
    import uvicorn

    print("Starting server...")
    port = int(os.getenv("UVICORN_PORT", "9021"))
    host = os.getenv("UVICORN_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)

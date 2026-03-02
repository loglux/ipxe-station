"""iPXE menu management routes."""

import re

from fastapi import APIRouter, Response

from app.backend.ipxe_manager import iPXEManager
from app.backend.ipxe_schema import IpxeMenuModel, menu_to_model, model_to_menu

from .state import IPXE_ROOT, TFTP_ROOT, add_log, load_settings

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


def _parse_boot_ipxe(script_content: str) -> dict:
    """Parse boot.ipxe script and extract menu structure."""
    entries = []
    lines = script_content.split("\n")

    in_start_menu = False
    in_submenu = None

    for line in lines:
        line = line.strip()

        if line == ":start":
            in_start_menu = True
            continue
        elif line.startswith(":submenu_"):
            in_submenu = line[1:]  # Remove ':' prefix
            continue
        elif line.startswith(":") and in_start_menu:
            in_start_menu = False
        elif line.startswith(":") and in_submenu:
            in_submenu = None

        if line.startswith("item ") and not line.startswith("item --gap"):
            parts = line.split(None, 2)
            if len(parts) >= 3:
                name = parts[1]
                title = parts[2]

                is_submenu = title.endswith("-->")
                if is_submenu:
                    title = title[:-3].strip()

                # Skip auto-generated entries — the menu generator always adds these
                if name.startswith("back_") or name in ["shell", "reboot", "exit"]:
                    continue

                if is_submenu:
                    entry_type = "submenu"
                    detected_mode = "netboot"
                else:
                    entry_type = "boot"
                    # Detect boot_mode from auto-generated prefix, then strip it from title
                    _prefix_map = {
                        "[NET]": "netboot",
                        "[LIVE]": "live",
                        "[RESCUE]": "rescue",
                        "[BOOT]": "custom",
                        "[SHELL]": "custom",
                        "[REBOOT]": "custom",
                        "[EXIT]": "custom",
                    }
                    detected_mode = None
                    # Strip ALL known prefixes; last one wins for boot_mode
                    while True:
                        matched = False
                        for _prefix, _mode in _prefix_map.items():
                            if title.startswith(_prefix):
                                title = title[len(_prefix) :].strip()
                                detected_mode = _mode
                                matched = True
                                break
                        if not matched:
                            break
                    if detected_mode is None:
                        detected_mode = "rescue"  # no label prefix → rescue (neutral)

                entry = {
                    "name": name,
                    "title": title,
                    "entry_type": entry_type,
                    "enabled": True,
                    "order": len(entries),
                    "parent": in_submenu.replace("submenu_", "") if in_submenu else None,
                    "boot_mode": detected_mode,
                }
                entries.append(entry)

    current_label = None
    for i, line in enumerate(lines):
        line = line.strip()

        if (
            line.startswith(":")
            and not line.startswith(":start")
            and not line.startswith(":submenu")
        ):
            current_label = line[1:]

            for entry in entries:
                if entry["name"] == current_label and entry["entry_type"] == "boot":
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
                            try:
                                cmdline_match = re.search(r"imgargs\s+\w+\s+(.+)", next_line)
                                if cmdline_match:
                                    entry["cmdline"] = (
                                        cmdline_match.group(1).replace(" ---", "").strip()
                                    )
                            except (IndexError, AttributeError):
                                pass
                        elif next_line.startswith("boot"):
                            break
                        elif next_line.startswith(":"):
                            break

                    entry.setdefault("kernel", "")
                    entry.setdefault("initrd", "")
                    entry.setdefault("cmdline", "")
                    entry.setdefault("description", "")
                    entry.setdefault("url", "")
                    entry.setdefault("boot_mode", "rescue")
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


@ipxe_router.get("/menu/structure")
def load_menu_structure():
    """Load the saved menu structure (menu.json) or parse from boot.ipxe."""
    import json

    menu_json_path = IPXE_ROOT / "menu.json"
    boot_ipxe_path = IPXE_ROOT / "boot.ipxe"

    if menu_json_path.exists():
        try:
            with open(menu_json_path, "r") as f:
                menu_data = json.load(f)
            # Only trust menu.json if it has actual entries; otherwise fall through to boot.ipxe
            if menu_data.get("entries"):
                return {
                    "success": True,
                    "message": "Menu structure loaded from menu.json",
                    "menu": menu_data,
                    "source": "json",
                }
            add_log("system", "info", "menu.json has no entries, falling back to boot.ipxe")
        except Exception as e:
            add_log(
                "system",
                "warning",
                f"Failed to parse menu.json, falling back to boot.ipxe: {str(e)}",
            )

    if boot_ipxe_path.exists():
        try:
            with open(boot_ipxe_path, "r") as f:
                script_content = f.read()

            menu_data = _parse_boot_ipxe(script_content)

            try:
                with open(menu_json_path, "w") as f:
                    json.dump(menu_data, f, indent=2)
            except Exception as e:
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

    ok, save_msg = ipxe_manager.save_menu(menu_dc)

    if ok:
        add_log("system", "info", f"Menu saved successfully: {len(menu.entries)} entries")
        menu_json_path = IPXE_ROOT / "menu.json"
        try:
            with open(menu_json_path, "w") as f:
                json.dump(menu.model_dump(), f, indent=2)
        except Exception as e:
            save_msg += f" (Warning: Failed to save menu.json: {str(e)})"
            add_log("system", "warning", f"Failed to save menu.json: {str(e)}")

        # Keep TFTP boot.ipxe as a chain script so TFTP clients always load the HTTP menu.
        # This guards against stale TFTP copies when the proxy DHCP is temporarily offline.
        tftp_boot_ipxe = TFTP_ROOT / "boot.ipxe"
        _s = load_settings()
        chain_script = (
            "#!ipxe\n"
            "dhcp\n"
            "echo Booting iPXE Station...\n"
            f"chain http://{_s.server_ip}:{_s.http_port}/ipxe/boot.ipxe"
            " || echo Chain failed: ${{errno}}\n"
            "shell\n"
        )
        try:
            with open(tftp_boot_ipxe, "w") as f:
                f.write(chain_script)
        except Exception as e:
            add_log("system", "warning", f"Failed to update TFTP boot.ipxe: {str(e)}")
    else:
        add_log("system", "error", f"Menu save failed: {message}")

    return {
        "valid": ok,
        "message": save_msg if ok else message,
        "warnings": warnings,
        "script": script_content if ok else "",
        "config_path": str(ipxe_manager.config_path),
    }

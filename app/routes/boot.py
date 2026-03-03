"""Boot file management routes (autoexec, TFTP files, boot ping)."""

import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .state import HTTP_ROOT, TFTP_ROOT, _record_boot_event, add_log, load_settings, save_settings

boot_router = APIRouter(prefix="/api/boot", tags=["boot"])

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


class AutoexecTemplateRequest(BaseModel):
    template: str
    next_server: str = os.getenv("PXE_SERVER_IP", "192.168.1.1")
    http_port: int = 9021


class AutoexecSaveRequest(BaseModel):
    content: str = ""


class PreseedSaveRequest(BaseModel):
    profile: str = "debian_minimal"
    content: str = ""
    activate: bool = True


class PreseedTemplateRequest(BaseModel):
    template: str
    profile: str = "debian_minimal"
    activate: bool = True


class PreseedActivateRequest(BaseModel):
    profile: str


PRESEED_TEMPLATES = {
    "debian_minimal": {
        "name": "Debian Minimal",
        "description": "Minimal unattended Debian install with DHCP and automatic partitioning.",
        "content": """# Debian preseed template (minimal)
d-i debian-installer/locale string en_US.UTF-8
d-i keyboard-configuration/xkb-keymap select us
d-i netcfg/choose_interface select auto
d-i netcfg/get_hostname string debian
d-i netcfg/get_domain string local

d-i mirror/country string manual
d-i mirror/http/hostname string deb.debian.org
d-i mirror/http/directory string /debian
d-i mirror/http/proxy string

d-i passwd/root-login boolean false
d-i passwd/user-fullname string Debian User
d-i passwd/username string debian
d-i passwd/user-password password debian
d-i passwd/user-password-again password debian

d-i clock-setup/utc boolean true
d-i time/zone string UTC

d-i partman-auto/method string regular
d-i partman-auto/choose_recipe select atomic
d-i partman-partitioning/confirm_write_new_label boolean true
d-i partman/choose_partition select finish
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true

tasksel tasksel/first multiselect standard, ssh-server
d-i pkgsel/include string openssh-server curl
d-i finish-install/reboot_in_progress note
""",
    },
    "debian_desktop": {
        "name": "Debian Desktop",
        "description": "Automated Debian install with GNOME desktop task selection.",
        "content": """# Debian preseed template (desktop)
d-i debian-installer/locale string en_US.UTF-8
d-i keyboard-configuration/xkb-keymap select us
d-i netcfg/choose_interface select auto
d-i netcfg/get_hostname string debian-desktop
d-i netcfg/get_domain string local

d-i mirror/country string manual
d-i mirror/http/hostname string deb.debian.org
d-i mirror/http/directory string /debian
d-i mirror/http/proxy string

d-i passwd/root-login boolean false
d-i passwd/user-fullname string Debian User
d-i passwd/username string debian
d-i passwd/user-password password debian
d-i passwd/user-password-again password debian

d-i clock-setup/utc boolean true
d-i time/zone string UTC

d-i partman-auto/method string regular
d-i partman-auto/choose_recipe select atomic
d-i partman-partitioning/confirm_write_new_label boolean true
d-i partman/choose_partition select finish
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true

tasksel tasksel/first multiselect standard, gnome-desktop
d-i pkgsel/include string openssh-server curl
d-i finish-install/reboot_in_progress note
""",
    },
}

_PROFILE_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _ensure_preseed_dir() -> Path:
    path = HTTP_ROOT / "preseed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validate_profile_name(name: str) -> str:
    profile = (name or "").strip()
    if not profile or not _PROFILE_RE.fullmatch(profile):
        raise HTTPException(status_code=400, detail="Invalid preseed profile name")
    return profile


def _profile_path(profile: str) -> Path:
    return _ensure_preseed_dir() / f"{profile}.cfg"


def _active_profile_name() -> str:
    return load_settings().active_preseed_profile or "debian_minimal"


def _list_preseed_profiles() -> list[str]:
    preseed_dir = _ensure_preseed_dir()
    return sorted(path.stem for path in preseed_dir.glob("*.cfg") if path.is_file())


def _sync_preseed_alias(profile: str):
    """Keep /preseed.cfg as a compatibility alias for the active profile."""
    profile = _validate_profile_name(profile)
    source = _profile_path(profile)
    alias = HTTP_ROOT / "preseed.cfg"
    if not source.exists():
        raise HTTPException(status_code=404, detail=f"Preseed profile not found: {profile}")

    alias.write_text(source.read_text())
    settings = load_settings()
    settings.active_preseed_profile = profile
    save_settings(settings)


def _ensure_default_preseed_profile():
    """Seed the default profile on first use so the feature is self-contained."""
    default_profile = "debian_minimal"
    default_path = _profile_path(default_profile)
    if not default_path.exists():
        default_path.write_text(PRESEED_TEMPLATES[default_profile]["content"])
    try:
        _sync_preseed_alias(_active_profile_name() if default_path.exists() else default_profile)
    except HTTPException:
        _sync_preseed_alias(default_profile)


@boot_router.get("/ping")
async def boot_ping(request: Request, stage: str = "beacon"):
    """Lightweight endpoint for iPXE scripts to confirm execution reached HTTP."""
    client_ip = request.client.host if request.client else "unknown"
    _record_boot_event(
        client_ip,
        "beacon",
        f"Boot beacon received at stage '{stage}'",
        protocol="http",
        filename="boot-ping",
    )
    return {"success": True, "client_ip": client_ip, "stage": stage}


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
def save_autoexec(payload: AutoexecSaveRequest):
    """Save autoexec.ipxe content."""
    autoexec_path = TFTP_ROOT / "autoexec.ipxe"

    try:
        content = payload.content

        with open(autoexec_path, "w") as f:
            f.write(content)

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


@boot_router.delete("/autoexec")
def delete_autoexec():
    """Delete autoexec.ipxe so boot flow can bypass the optional bootstrap script."""
    autoexec_path = TFTP_ROOT / "autoexec.ipxe"

    if not autoexec_path.exists():
        return {"success": True, "message": "autoexec.ipxe already disabled"}

    try:
        autoexec_path.unlink()
        add_log("system", "info", "autoexec.ipxe deleted (optional bootstrap disabled)")
        return {"success": True, "message": "autoexec.ipxe deleted"}
    except Exception as e:
        add_log("system", "error", f"Failed to delete autoexec.ipxe: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete autoexec.ipxe: {str(e)}")


@boot_router.post("/autoexec/apply-template")
def apply_autoexec_template(request: AutoexecTemplateRequest):
    """Apply a template to autoexec.ipxe with variable substitution."""
    if request.template not in AUTOEXEC_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown template: {request.template}")

    template = AUTOEXEC_TEMPLATES[request.template]
    content = template["content"]

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


@boot_router.get("/preseed")
def get_preseed(profile: str | None = None):
    """Get preseed profile content; defaults to the active profile."""
    _ensure_default_preseed_profile()
    selected = _validate_profile_name(profile) if profile else _active_profile_name()
    preseed_path = _profile_path(selected)

    if not preseed_path.exists():
        return {"exists": False, "content": "", "message": f"Preseed profile not found: {selected}"}

    try:
        with open(preseed_path, "r") as f:
            content = f.read()
        return {
            "exists": True,
            "content": content,
            "path": str(preseed_path),
            "profile": selected,
            "active_profile": _active_profile_name(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read preseed profile: {str(e)}")


@boot_router.get("/preseed/profiles")
def get_preseed_profiles():
    """List available preseed profiles and the active one."""
    _ensure_default_preseed_profile()
    return {
        "profiles": _list_preseed_profiles(),
        "active_profile": _active_profile_name(),
    }


@boot_router.post("/preseed")
def save_preseed(payload: PreseedSaveRequest):
    """Save a preseed profile and optionally activate it."""
    _ensure_default_preseed_profile()
    profile = _validate_profile_name(payload.profile)
    preseed_path = _profile_path(profile)

    try:
        content = payload.content
        with open(preseed_path, "w") as f:
            f.write(content)

        if payload.activate:
            _sync_preseed_alias(profile)

        add_log("system", "info", f"preseed profile '{profile}' saved ({len(content)} bytes)")
        return {
            "success": True,
            "message": f"Preseed profile '{profile}' saved successfully",
            "path": str(preseed_path),
            "size": len(content),
            "profile": profile,
            "active_profile": _active_profile_name(),
        }
    except Exception as e:
        add_log("system", "error", f"Failed to save preseed profile '{profile}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save preseed profile: {str(e)}")


@boot_router.delete("/preseed")
def delete_preseed(profile: str | None = None):
    """Delete a preseed profile from HTTP root."""
    _ensure_default_preseed_profile()
    selected = _validate_profile_name(profile) if profile else _active_profile_name()
    preseed_path = _profile_path(selected)

    if not preseed_path.exists():
        return {"success": True, "message": f"Preseed profile '{selected}' already absent"}

    try:
        preseed_path.unlink()

        profiles = _list_preseed_profiles()
        settings = load_settings()
        alias = HTTP_ROOT / "preseed.cfg"
        if selected == settings.active_preseed_profile:
            if profiles:
                settings.active_preseed_profile = profiles[0]
                save_settings(settings)
                _sync_preseed_alias(profiles[0])
            else:
                alias.unlink(missing_ok=True)
                settings.active_preseed_profile = "debian_minimal"
                save_settings(settings)

        add_log("system", "info", f"Preseed profile '{selected}' deleted")
        return {
            "success": True,
            "message": f"Preseed profile '{selected}' deleted",
            "active_profile": _active_profile_name() if _list_preseed_profiles() else None,
        }
    except Exception as e:
        add_log("system", "error", f"Failed to delete preseed profile '{selected}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete preseed profile: {str(e)}")


@boot_router.post("/preseed/activate")
def activate_preseed_profile(request: PreseedActivateRequest):
    """Activate an existing preseed profile for /preseed.cfg."""
    _ensure_default_preseed_profile()
    profile = _validate_profile_name(request.profile)
    _sync_preseed_alias(profile)
    add_log("system", "info", f"Preseed profile '{profile}' activated")
    return {"success": True, "active_profile": profile}


@boot_router.get("/preseed/templates")
def get_preseed_templates():
    """Get available preseed.cfg templates."""
    return {
        "templates": {
            key: {"name": tpl["name"], "description": tpl["description"]}
            for key, tpl in PRESEED_TEMPLATES.items()
        }
    }


@boot_router.post("/preseed/apply-template")
def apply_preseed_template(request: PreseedTemplateRequest):
    """Apply a preseed template into a named profile."""
    _ensure_default_preseed_profile()
    if request.template not in PRESEED_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown template: {request.template}")

    template = PRESEED_TEMPLATES[request.template]
    content = template["content"]
    profile = _validate_profile_name(request.profile)
    preseed_path = _profile_path(profile)

    try:
        with open(preseed_path, "w") as f:
            f.write(content)

        if request.activate:
            _sync_preseed_alias(profile)

        add_log(
            "system",
            "info",
            f"Applied preseed template '{template['name']}' to profile '{profile}'",
        )
        return {
            "success": True,
            "message": f"Applied template: {template['name']}",
            "content": content,
            "template": request.template,
            "profile": profile,
            "active_profile": _active_profile_name(),
        }
    except Exception as e:
        add_log("system", "error", f"Failed to apply preseed template: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to apply preseed template: {str(e)}")


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

"""Boot file management routes (autoexec, TFTP files, boot ping)."""

import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .state import TFTP_ROOT, _record_boot_event, add_log

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

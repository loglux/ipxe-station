from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, RedirectResponse
import os
from pathlib import Path
from fastapi import APIRouter
from typing import List
import shutil
import requests

from app.backend.ipxe_manager import iPXEManager
from app.backend.ipxe_schema import IpxeMenuModel, model_to_menu

app = FastAPI(title="iPXE Station", description="Network Boot Server")

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

# Mount static file serving for HTTP boot
app.mount("/http", StaticFiles(directory=str(HTTP_ROOT)), name="http")

# Mount iPXE files
@app.get("/ipxe/{filename}")
@app.head("/ipxe/{filename}")
async def serve_ipxe(filename: str):
    """Serve iPXE files"""
    file_path = IPXE_ROOT / filename
    if file_path.exists():
        return FileResponse(
            file_path,
        media_type="text/plain",
        headers={"Cache-Control": "no-cache"})
    return Response("File not found", status_code=404)

# Mount TFTP files (for HTTP access if needed)
@app.get("/tftp/{filename}")
async def serve_tftp(filename: str):
    """Serve TFTP files via HTTP"""
    file_path = TFTP_ROOT / filename
    if file_path.exists():
        return FileResponse(file_path)
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
        "ipxe_files": len(list(IPXE_ROOT.glob("*")))
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
        # common names
        for name in ["vmlinuz", "linux"]:
            candidate = path / name
            if candidate.exists():
                kernel = f"{path.name}/{name}"
                break
        for name in ["initrd", "initrd.img", "initrd.lz"]:
            candidate = path / name
            if candidate.exists():
                initrd = f"{path.name}/{name}"
                break
        for item in path.glob("*.iso"):
            iso = f"{path.name}/{item.name}"
            break
        for item in path.glob("*.wim"):
            wim = f"{path.name}/{item.name}"
            break
        results.append({"version": version, "kernel": kernel, "initrd": initrd, "iso": iso, "wim": wim})
    return results


# API: iPXE config validation/generation
ipxe_router = APIRouter(prefix="/api/ipxe", tags=["ipxe"])
ipxe_manager = iPXEManager(config_path=IPXE_ROOT / "boot.ipxe")


@ipxe_router.post("/validate")
def validate_ipxe(menu: IpxeMenuModel):
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


@ipxe_router.post("/menu/save")
def save_menu(menu: IpxeMenuModel):
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
    return {
        "valid": ok,
        "message": save_msg if ok else message,
        "warnings": warnings,
        "script": script_content if ok else "",
        "config_path": str(ipxe_manager.config_path),
    }


app.include_router(ipxe_router)


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
    return {"ubuntu": ubuntu, "debian": debian, "windows": windows, "rescue": rescue}


@app.post("/api/assets/download")
def download_asset(url: str, dest: str = ""):
    """Download a remote asset into /srv/http/<dest> (relative)."""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Only http/https URLs allowed")
    target = HTTP_ROOT / dest if dest else HTTP_ROOT / Path(url).name
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(target, "wb") as fh:
                shutil.copyfileobj(r.raw, fh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Download failed: {exc}")
    return {"saved": str(target.relative_to(HTTP_ROOT))}


@app.post("/api/assets/upload")
async def upload_asset(file: UploadFile = File(...), dest: str = ""):
    """Upload a file into /srv/http/<dest> (relative)."""
    safe_dest = dest.strip("/") if dest else ""
    target_dir = HTTP_ROOT / safe_dest
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file.filename
    try:
        with open(target_path, "wb") as fh:
            content = await file.read()
            fh.write(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")
    return {"saved": str(target_path.relative_to(HTTP_ROOT))}

# Serve built frontend (Vite)
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="ui")
else:
    print("Warning: Frontend dist directory not found. Build the frontend first.")

if __name__ == "__main__":
    import uvicorn
    print("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

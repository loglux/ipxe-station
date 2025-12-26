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
from app.backend.dhcp_helper import DHCPConfigGenerator, DHCPConfig, DHCPValidator
from pydantic import BaseModel
import threading
import time

app = FastAPI(title="iPXE Station", description="Network Boot Server")

# Global dictionary to track download progress
download_progress = {}

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


class DownloadRequest(BaseModel):
    url: str
    dest: str = ""


@app.post("/api/assets/download")
def download_asset(request: DownloadRequest):
    """Download a remote asset into /srv/http/<dest> (relative) with progress tracking."""
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Only http/https URLs allowed")

    target = HTTP_ROOT / request.dest if request.dest else HTTP_ROOT / Path(request.url).name
    target.parent.mkdir(parents=True, exist_ok=True)

    # Create progress tracking key
    progress_key = str(target.relative_to(HTTP_ROOT))

    try:
        with requests.get(request.url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))

            # Initialize progress tracking
            download_progress[progress_key] = {
                "downloaded": 0,
                "total": total_size,
                "percentage": 0,
                "status": "downloading"
            }

            downloaded = 0
            with open(target, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
                        downloaded += len(chunk)

                        # Update progress every MB or so
                        if downloaded % (1024 * 1024) < 8192 or downloaded == total_size:
                            percentage = (downloaded / total_size * 100) if total_size > 0 else 0
                            download_progress[progress_key] = {
                                "downloaded": downloaded,
                                "total": total_size,
                                "percentage": round(percentage, 1),
                                "status": "downloading"
                            }

            # Mark as complete
            download_progress[progress_key] = {
                "downloaded": downloaded,
                "total": total_size,
                "percentage": 100,
                "status": "complete"
            }

    except Exception as exc:
        download_progress[progress_key] = {
            "downloaded": 0,
            "total": 0,
            "percentage": 0,
            "status": "error",
            "error": str(exc)
        }
        raise HTTPException(status_code=500, detail=f"Download failed: {exc}")

    return {"saved": str(target.relative_to(HTTP_ROOT))}


@app.get("/api/assets/download/progress/{file_path:path}")
def get_download_progress(file_path: str):
    """Get download progress for a specific file."""
    if file_path in download_progress:
        return download_progress[file_path]
    else:
        return {"status": "not_found"}


@app.get("/api/assets/download/progress")
def get_all_download_progress():
    """Get all active download progress."""
    return {"downloads": download_progress}


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


class ExtractISORequest(BaseModel):
    iso_path: str
    kernel_path: str = ""
    initrd_path: str = ""
    dest_dir: str = ""
    kernel_filename: str = "vmlinuz"
    initrd_filename: str = "initrd"


@app.post("/api/assets/extract-iso")
def extract_iso(request: ExtractISORequest):
    """Extract kernel and initrd from an ISO file using 7zip."""
    import subprocess

    # Resolve ISO path (relative to HTTP_ROOT)
    iso_file = HTTP_ROOT / request.iso_path
    if not iso_file.exists():
        raise HTTPException(status_code=404, detail=f"ISO file not found: {request.iso_path}")

    # Determine destination directory
    dest_dir = HTTP_ROOT / request.dest_dir if request.dest_dir else iso_file.parent / iso_file.stem
    dest_dir.mkdir(parents=True, exist_ok=True)

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
            lines = iso_contents.split('\n')
            for line in lines:
                if not kernel_in_iso and any(x in line.lower() for x in ['vmlinuz', 'linux', 'kernel']):
                    # Extract path from 7z output
                    parts = line.split()
                    if len(parts) >= 6:
                        potential_path = ' '.join(parts[5:])
                        if 'vmlinuz' in potential_path or 'linux' in potential_path:
                            kernel_in_iso = potential_path

                if not initrd_in_iso and any(x in line.lower() for x in ['initrd', 'initramfs', 'sysresccd.img']):
                    parts = line.split()
                    if len(parts) >= 6:
                        potential_path = ' '.join(parts[5:])
                        if any(x in potential_path.lower() for x in ['initrd', 'initramfs', 'sysresccd.img']):
                            initrd_in_iso = potential_path

        extracted_files = {}

        # Extract kernel
        if kernel_in_iso:
            extract_cmd = ["7z", "e", str(iso_file), f"-o{dest_dir}", kernel_in_iso, "-y"]
            subprocess.run(extract_cmd, check=True, capture_output=True)

            # Rename if necessary
            extracted_name = Path(kernel_in_iso).name
            source_file = dest_dir / extracted_name
            target_file = dest_dir / request.kernel_filename

            if source_file.exists() and source_file != target_file:
                source_file.rename(target_file)
                extracted_files['kernel'] = str(target_file.relative_to(HTTP_ROOT))
            elif target_file.exists():
                extracted_files['kernel'] = str(target_file.relative_to(HTTP_ROOT))

        # Extract initrd
        if initrd_in_iso:
            extract_cmd = ["7z", "e", str(iso_file), f"-o{dest_dir}", initrd_in_iso, "-y"]
            subprocess.run(extract_cmd, check=True, capture_output=True)

            # Rename if necessary
            extracted_name = Path(initrd_in_iso).name
            source_file = dest_dir / extracted_name
            target_file = dest_dir / request.initrd_filename

            if source_file.exists() and source_file != target_file:
                source_file.rename(target_file)
                extracted_files['initrd'] = str(target_file.relative_to(HTTP_ROOT))
            elif target_file.exists():
                extracted_files['initrd'] = str(target_file.relative_to(HTTP_ROOT))

        # Create symlink to original ISO in dest directory
        iso_link = dest_dir / iso_file.name
        if not iso_link.exists():
            iso_link.symlink_to(iso_file)
            extracted_files['iso'] = str(iso_link.relative_to(HTTP_ROOT))

        return {
            "success": True,
            "dest_dir": str(dest_dir.relative_to(HTTP_ROOT)),
            "extracted_files": extracted_files,
            "kernel_path": kernel_in_iso,
            "initrd_path": initrd_in_iso
        }

    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {e.stderr.decode() if e.stderr else str(e)}"
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

        soup = BeautifulSoup(response.text, 'html.parser')
        versions_dict = {}  # Use dict to deduplicate by version number

        # Find all version folders (format: X.Y.Z/)
        for link in soup.find_all('a', href=True):
            href = link['href']
            # Match version pattern like /projects/systemrescuecd/files/sysresccd-x86/11.02/
            match = re.search(r'/sysresccd-x86/(\d+\.\d+(?:\.\d+)?)', href)
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
                        "size_est": "~950 MB"
                    }

        # Convert to list and sort by version (newest first)
        versions = list(versions_dict.values())
        versions.sort(key=lambda x: [int(n) for n in x['version'].split('.')], reverse=True)
        return {"versions": versions[:10]}  # Return top 10 versions

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch versions: {exc}")


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
    tftp_port: int = 69
):
    """Generate DHCP configuration for specified server type"""
    try:
        config = DHCPConfig(
            pxe_server_ip=pxe_server_ip,
            http_port=http_port,
            tftp_port=tftp_port,
            server_type=server_type
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


# Serve built frontend (Vite)
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="ui")
else:
    print("Warning: Frontend dist directory not found. Build the frontend first.")

if __name__ == "__main__":
    import uvicorn
    print("Starting server...")
    port = int(os.getenv("UVICORN_PORT", "8000"))
    host = os.getenv("UVICORN_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)

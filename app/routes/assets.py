"""Asset management routes (download, upload, extract, catalog)."""

import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from .state import (
    HTTP_ROOT,
    _list_relative_files,
    _resolve_within_root,
    _scan_distro_versions,
    _validate_filename,
    add_log,
    download_progress,
    download_progress_lock,
)

assets_router = APIRouter(prefix="/api/assets", tags=["assets"])


class DownloadRequest(BaseModel):
    url: str
    dest: str = ""


class ExtractISORequest(BaseModel):
    iso_path: str
    kernel_path: str = ""
    initrd_path: str = ""
    dest_dir: str = ""
    kernel_filename: str = "vmlinuz"
    initrd_filename: str = "initrd"


def _extract_full_iso(iso_path: Path, dest_dir: Path) -> dict:
    """Helper function to extract entire ISO contents to destination directory."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        extract_cmd = ["7z", "x", str(iso_path), f"-o{dest_dir}", "-y"]
        subprocess.run(extract_cmd, check=True, capture_output=True, text=True)

        file_count = sum(1 for _ in dest_dir.rglob("*") if _.is_file())

        return {"success": True, "dest_dir": str(dest_dir), "file_count": file_count}
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": f"Extraction failed: {e.stderr if e.stderr else str(e)}",
        }
    except Exception as exc:
        return {"success": False, "error": f"Extraction failed: {exc}"}


@assets_router.get("")
def list_assets():
    """List available boot assets in http/tftp/ipxe roots (shallow)."""
    from .state import IPXE_ROOT, TFTP_ROOT

    return {
        "http": _list_relative_files(HTTP_ROOT, max_depth=3),
        "tftp": _list_relative_files(TFTP_ROOT, max_depth=3),
        "ipxe": _list_relative_files(IPXE_ROOT, max_depth=3),
    }


@assets_router.get("/catalog")
def assets_catalog():
    """Return discovered distro assets by version."""
    ubuntu = _scan_distro_versions("ubuntu", HTTP_ROOT)
    debian = _scan_distro_versions("debian", HTTP_ROOT)
    windows = _scan_distro_versions("windows", HTTP_ROOT)
    rescue = _scan_distro_versions("rescue", HTTP_ROOT)
    kaspersky = _scan_distro_versions("kaspersky", HTTP_ROOT)

    return {
        "ubuntu": ubuntu,
        "debian": debian,
        "windows": windows,
        "rescue": rescue,
        "kaspersky": kaspersky,
    }


@assets_router.get("/boot-recipe")
def assets_boot_recipe(version_path: str, scenario: str):
    """Return boot options (kernel/initrd/cmdline) for a distro version + scenario.

    - **version_path**: directory name, e.g. ``ubuntu-22.04``
    - **scenario**: wizard scenario ID, e.g. ``ubuntu_live``
    """
    from app.backend.boot_recipes import get_recipe
    from app.backend.config import settings

    # Derive catalog prefix from the directory name (e.g. "ubuntu-22.04" → "ubuntu")
    prefix = version_path.split("-")[0]

    versions = _scan_distro_versions(prefix, HTTP_ROOT)
    # version ID is everything after "prefix-"
    version_id = version_path[len(prefix) + 1 :]
    entry = next((v for v in versions if v["version"] == version_id), None)

    if entry is None:
        raise HTTPException(
            status_code=404, detail=f"Version '{version_path}' not found in catalog"
        )

    return get_recipe(scenario, entry, settings.pxe_server_ip, settings.http_port)


@assets_router.post("/download")
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

    progress_key = str(target.relative_to(HTTP_ROOT.resolve()))

    try:
        with requests.get(request.url, stream=True, timeout=(30, 600)) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))

            with download_progress_lock:
                download_progress[progress_key] = {
                    "downloaded": 0,
                    "total": total_size,
                    "percentage": 0,
                    "status": "downloading",
                }

            add_log("download", "info", f"Started downloading {progress_key} ({total_size} bytes)")

            downloaded = 0
            with open(target, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
                        downloaded += len(chunk)

                        if downloaded % (1024 * 1024) < 8192 or downloaded == total_size:
                            percentage = (downloaded / total_size * 100) if total_size > 0 else 0
                            with download_progress_lock:
                                download_progress[progress_key] = {
                                    "downloaded": downloaded,
                                    "total": total_size,
                                    "percentage": round(percentage, 1),
                                    "status": "downloading",
                                }

        with download_progress_lock:
            download_progress[progress_key] = {
                "downloaded": downloaded,
                "total": total_size,
                "percentage": 100,
                "status": "complete",
            }

        add_log("download", "info", f"Completed downloading {progress_key} ({downloaded} bytes)")

        if target.suffix.lower() == ".iso":
            with download_progress_lock:
                download_progress[progress_key]["status"] = "extracting"
            add_log("download", "info", f"Starting ISO extraction for {progress_key}")

            extract_dir = target.parent
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
                    f"Extracted {extraction_result.get('file_count', 0)} files from {progress_key}",  # noqa: E501
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
                    f"ISO extraction failed for {progress_key}: "
                    f"{extraction_result.get('error', 'Unknown error')}",
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


@assets_router.get("/download/progress/{file_path:path}")
def get_download_progress(file_path: str):
    """Get download progress for a specific file."""
    with download_progress_lock:
        if file_path in download_progress:
            return download_progress[file_path].copy()
        else:
            return {"status": "not_found"}


@assets_router.get("/download/progress")
def get_all_download_progress():
    """Get all active download progress."""
    with download_progress_lock:
        return {"downloads": download_progress.copy()}


@assets_router.post("/upload")
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


@assets_router.post("/extract-iso")
def extract_iso(request: ExtractISORequest):
    """Extract kernel and initrd from an ISO file using 7zip."""
    iso_file = _resolve_within_root(HTTP_ROOT, request.iso_path, path_label="iso_path")
    if not iso_file.exists():
        raise HTTPException(status_code=404, detail=f"ISO file not found: {request.iso_path}")

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
        list_cmd = ["7z", "l", str(iso_file)]
        result = subprocess.run(list_cmd, capture_output=True, text=True, check=True)
        iso_contents = result.stdout

        kernel_in_iso = request.kernel_path
        initrd_in_iso = request.initrd_path

        if not kernel_in_iso or not initrd_in_iso:
            lines = iso_contents.split("\n")
            for line in lines:
                if not kernel_in_iso and any(
                    x in line.lower() for x in ["vmlinuz", "linux", "kernel"]
                ):
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

        if kernel_in_iso:
            extract_cmd = ["7z", "e", str(iso_file), f"-o{dest_dir}", kernel_in_iso, "-y"]
            subprocess.run(extract_cmd, check=True, capture_output=True)

            extracted_name = Path(kernel_in_iso).name
            source_file = dest_dir / extracted_name
            target_file = dest_dir / kernel_filename

            if source_file.exists() and source_file != target_file:
                source_file.rename(target_file)
                extracted_files["kernel"] = str(target_file.relative_to(HTTP_ROOT))
            elif target_file.exists():
                extracted_files["kernel"] = str(target_file.relative_to(HTTP_ROOT))

        if initrd_in_iso:
            extract_cmd = ["7z", "e", str(iso_file), f"-o{dest_dir}", initrd_in_iso, "-y"]
            subprocess.run(extract_cmd, check=True, capture_output=True)

            extracted_name = Path(initrd_in_iso).name
            source_file = dest_dir / extracted_name
            target_file = dest_dir / initrd_filename

            if source_file.exists() and source_file != target_file:
                source_file.rename(target_file)
                extracted_files["initrd"] = str(target_file.relative_to(HTTP_ROOT))
            elif target_file.exists():
                extracted_files["initrd"] = str(target_file.relative_to(HTTP_ROOT))

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


@assets_router.get("/versions/systemrescue")
def get_systemrescue_versions():
    """Fetch available SystemRescue versions from SourceForge."""
    try:
        import re

        from bs4 import BeautifulSoup

        url = "https://sourceforge.net/projects/systemrescuecd/files/sysresccd-x86/"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        versions_dict = {}

        for link in soup.find_all("a", href=True):
            href = link["href"]
            match = re.search(r"/sysresccd-x86/(\d+\.\d+(?:\.\d+)?)", href)
            if match:
                version = match.group(1)
                if version not in versions_dict:
                    iso_name = f"systemrescue-{version}-amd64.iso"
                    download_url = (
                        f"https://sourceforge.net/projects/systemrescuecd/files/"
                        f"sysresccd-x86/{version}/{iso_name}/download"
                    )

                    versions_dict[version] = {
                        "version": version,
                        "name": f"SystemRescue {version}",
                        "iso_url": download_url,
                        "iso_name": iso_name,
                        "size_est": "~950 MB",
                    }

        versions = list(versions_dict.values())
        versions.sort(key=lambda x: [int(n) for n in x["version"].split(".")], reverse=True)
        return {"versions": versions[:10]}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch versions: {exc}")


@assets_router.get("/versions/kaspersky")
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

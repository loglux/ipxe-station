"""Asset management routes (download, upload, extract, catalog)."""

import shutil
import subprocess
import threading
import time
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

_DOWNLOAD_PROGRESS_TTL = 3600  # seconds — completed/failed entries are dropped after 1 hour


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


def _autodetect_nfs_root() -> str:
    """Return NFS root path from showmount if NFS is running, else empty string.

    Used as a fallback when nfs_root is not configured in settings.
    The user can override this by setting nfs_root explicitly in Settings.
    """
    try:
        out = subprocess.run(
            ["showmount", "-e", "--no-headers", "127.0.0.1"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            exports = [line.split()[0] for line in out.stdout.splitlines() if line.strip()]
            if exports:
                return exports[0]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""


@assets_router.get("/boot-recipe")
def assets_boot_recipe(version_path: str, scenario: str):
    """Return boot options (kernel/initrd/cmdline) for a distro version + scenario.

    - **version_path**: directory name, e.g. ``ubuntu-22.04``
    - **scenario**: wizard scenario ID, e.g. ``ubuntu_live``
    """
    from app.backend.boot_recipes import get_recipe

    from .state import load_settings

    s = load_settings()

    # Use configured nfs_root if set; otherwise auto-detect from showmount.
    # Settings nfs_root acts as an explicit override (e.g. non-standard export path).
    nfs_root = s.nfs_root or _autodetect_nfs_root()

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

    return get_recipe(scenario, entry, s.server_ip, s.http_port, nfs_root=nfs_root)


@assets_router.post("/merge-squashfs")
def merge_squashfs(version_dir: str):
    """Merge all squashfs layers for a Ubuntu Server version into a single merged.squashfs.

    Allows fetching via HTTP (fetch=) without NFS or downloading the full ISO to RAM.
    The merge runs in a background thread; poll /api/assets/merge-progress for status.
    """
    version_path = _resolve_within_root(HTTP_ROOT, version_dir, path_label="version_dir")
    casper_dir = version_path / "casper"

    if not casper_dir.exists():
        raise HTTPException(status_code=404, detail=f"No casper/ directory in {version_dir}")

    # Collect non-hwe squashfs files sorted by layer depth (segment count in name)
    # e.g. ubuntu-server-minimal.squashfs (1) → .ubuntu-server (2) → .installer (3) → .generic (4)  # noqa: E501
    squashfs_files = sorted(
        (
            f
            for f in casper_dir.glob("*.squashfs")
            if "hwe" not in f.name and f.name != "merged.squashfs"
        ),
        key=lambda f: len(f.stem.split(".")),
    )
    if not squashfs_files:
        raise HTTPException(status_code=404, detail="No squashfs layers found in casper/")

    output = casper_dir / "merged.squashfs"
    progress_key = f"merge_{version_dir}"

    def _do_merge():
        tmp_dir = Path(f"/tmp/merge_{version_dir}")
        try:
            with download_progress_lock:
                download_progress[progress_key] = {
                    "status": "running",
                    "step": "Preparing…",
                    "progress": 0,
                }

            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
            tmp_dir.mkdir(parents=True)

            total = len(squashfs_files)
            for i, sqf in enumerate(squashfs_files):
                with download_progress_lock:
                    download_progress[progress_key][
                        "step"
                    ] = f"Extracting layer {i + 1}/{total}: {sqf.name}"
                    download_progress[progress_key]["progress"] = int(i / (total + 1) * 75)
                result = subprocess.run(
                    ["unsquashfs", "-f", "-no-xattrs", "-d", str(tmp_dir), str(sqf)],
                    capture_output=True,
                )
                # 0 = ok, 1/2 = partial errors (device nodes or hardlinks skipped in
                # containers — normal because overlayfs whiteouts require CAP_MKNOD)
                if result.returncode > 2:
                    result.check_returncode()

            # Strip device files (overlayfs whiteouts) — they can't be created in
            # containers and would cause mksquashfs to fail or produce an invalid image
            with download_progress_lock:
                download_progress[progress_key]["step"] = "Removing device nodes…"
            subprocess.run(
                ["find", str(tmp_dir), "(", "-type", "c", "-o", "-type", "b", ")", "-delete"],
                capture_output=True,
            )

            with download_progress_lock:
                download_progress[progress_key][
                    "step"
                ] = "Compressing merged.squashfs (this takes a few minutes)…"
                download_progress[progress_key]["progress"] = 80

            if output.exists():
                output.unlink()
            subprocess.run(
                ["mksquashfs", str(tmp_dir), str(output), "-noappend", "-comp", "xz"],
                check=True,
                capture_output=True,
            )

            size_mb = round(output.stat().st_size / 1024 / 1024)
            add_log("system", "info", f"merged.squashfs created for {version_dir} ({size_mb} MB)")
            with download_progress_lock:
                download_progress[progress_key] = {
                    "status": "done",
                    "step": f"Done — {size_mb} MB",
                    "progress": 100,
                    "completed_at": time.time(),
                }
        except Exception as e:
            add_log("system", "error", f"merge-squashfs failed for {version_dir}: {e}")
            with download_progress_lock:
                download_progress[progress_key] = {
                    "status": "error",
                    "step": str(e),
                    "progress": 0,
                    "completed_at": time.time(),
                }
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    threading.Thread(target=_do_merge, daemon=True).start()
    return {"status": "started", "progress_key": progress_key}


@assets_router.get("/merge-progress")
def get_merge_progress(version_dir: str):
    """Poll progress of a running or completed merge-squashfs operation."""
    progress_key = f"merge_{version_dir}"
    with download_progress_lock:
        return download_progress.get(progress_key, {"status": "not_started"})


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
                "completed_at": time.time(),
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
                    download_progress[progress_key]["completed_at"] = time.time()
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
                    download_progress[progress_key]["completed_at"] = time.time()
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
                "completed_at": time.time(),
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
    """Get all active download progress, dropping stale completed entries."""
    _terminal = {"complete", "extracted", "extraction_failed", "error"}
    now = time.time()
    with download_progress_lock:
        stale = [
            k
            for k, v in download_progress.items()
            if v.get("status") in _terminal
            and now - v.get("completed_at", now) > _DOWNLOAD_PROGRESS_TTL
        ]
        for k in stale:
            del download_progress[k]
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


@assets_router.get("/versions/ubuntu")
def get_ubuntu_versions():
    """Fetch available Ubuntu Server ISO versions from releases.ubuntu.com."""
    import re

    try:
        main_url = "https://releases.ubuntu.com/"
        resp = requests.get(main_url, timeout=10)
        resp.raise_for_status()

        # LTS releases have minor version == 04 (e.g. 22.04, 24.04)
        major_versions = re.findall(r'href="(\d+\.04)/"', resp.text)
        # Drop EOL (before 20.04)
        active = sorted({v for v in major_versions if float(v) >= 20.04}, reverse=True)

        result = []
        for major_ver in active[:6]:
            try:
                dir_resp = requests.get(f"{main_url}{major_ver}/", timeout=10)
                dir_resp.raise_for_status()

                server_isos = sorted(
                    set(re.findall(r"ubuntu-[\d.]+-live-server-amd64\.iso", dir_resp.text)),
                    key=lambda x: [int(n) for n in re.findall(r"\d+", x)],
                    reverse=True,
                )
                if not server_isos:
                    continue

                latest = server_isos[0]
                m = re.search(r"ubuntu-([\d.]+)-live-server", latest)
                full_ver = m.group(1) if m else major_ver
                result.append(
                    {
                        "version": major_ver,
                        "full_version": full_ver,
                        "name": f"Ubuntu {full_ver} LTS Server",
                        "iso_name": latest,
                        "iso_url": f"{main_url}{major_ver}/{latest}",
                        "dest_folder": f"ubuntu-{major_ver}",
                        "size_est": "~2.6 GB",
                    }
                )
            except Exception:
                continue

        return {"versions": result}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Ubuntu versions: {exc}")


@assets_router.get("/nfs-status")
def nfs_status():
    """Check whether an NFS server is running on the host and covers the required distro dirs."""
    import socket

    result = {
        "running": False,
        "rpcbind": False,
        "nfs": False,
        "exports": None,
        "covered": [],  # ubuntu/rescue/kaspersky dirs covered by an export
        "missing": [],  # dirs present on disk but not covered by any export
    }

    # Check ports 111 (rpcbind) and 2049 (NFS) — works because network_mode=host
    for port, key in ((111, "rpcbind"), (2049, "nfs")):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                result[key] = True
        except OSError:
            pass

    result["running"] = result["rpcbind"] and result["nfs"]

    # Try showmount -e to list exports
    exports: list[str] = []
    if result["running"]:
        try:
            out = subprocess.run(
                ["showmount", "-e", "--no-headers", "127.0.0.1"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if out.returncode == 0:
                exports = [line.split()[0] for line in out.stdout.splitlines() if line.strip()]
                result["exports"] = exports
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # showmount not installed — port check is enough

    # Include nfs_root from settings — gives frontend the configured host path
    from app.routes.state import load_settings as _load_settings

    _s = _load_settings()
    result["nfs_root"] = _s.nfs_root  # "" if not configured

    # Cross-check: which distro dirs on disk are covered by an NFS export or nfs_root?
    # showmount returns host paths; nfs_root is the explicit host path configured by user.
    all_paths = list(exports) + ([_s.nfs_root] if _s.nfs_root else [])
    distro_dirs = [p.name for p in HTTP_ROOT.iterdir() if p.is_dir()] if HTTP_ROOT.exists() else []
    for d in distro_dirs:
        covered = any(
            p.endswith(d) or f"/{d}/" in p or p.endswith("/http") or "/srv/http" in p
            for p in all_paths
        )
        if covered:
            result["covered"].append(d)
        else:
            result["missing"].append(d)

    return result


@assets_router.get("/check-url")
def check_url(url: str):
    """Check if a remote URL is accessible via HEAD request."""
    try:
        r = requests.head(url, allow_redirects=True, timeout=10)
        size = r.headers.get("content-length")
        return {
            "ok": r.status_code == 200,
            "status": r.status_code,
            "size": int(size) if size else None,
        }
    except Exception as exc:
        return {"ok": False, "status": None, "size": None, "error": str(exc)}

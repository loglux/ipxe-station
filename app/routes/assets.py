"""Asset management routes (download, upload, extract, catalog)."""

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from .state import (
    HTTP_ROOT,
    IPXE_ROOT,
    _list_relative_files,
    _resolve_within_root,
    _scan_distro_versions,
    _validate_filename,
    add_log,
    download_progress,
    download_progress_lock,
    load_settings,
)

assets_router = APIRouter(prefix="/api/assets", tags=["assets"])

_DOWNLOAD_PROGRESS_TTL = 3600  # seconds — completed/failed entries are dropped after 1 hour

DEBIAN_PRODUCTS = [
    {
        "id": "debian-12.10-netboot",
        "channel": "oldstable",
        "kind": "installer_bootstrap",
        "version": "12.10.0",
        "name": "Debian 12.10 Netboot Installer Files",
        "description": "Small Debian installer bootstrap: linux + initrd.gz for Netboot and Preseed.",  # noqa: E501
        "size_est": "~45 MB",
        "dest_folder": "debian-12.10",
        "kernel_url": "https://deb.debian.org/debian/dists/bookworm/main/installer-amd64/current/images/netboot/debian-installer/amd64/linux",
        "initrd_url": "https://deb.debian.org/debian/dists/bookworm/main/installer-amd64/current/images/netboot/debian-installer/amd64/initrd.gz",
        "files": {"kernel": "linux", "initrd": "initrd.gz"},
        "boot_targets": ["Debian Netboot", "Debian Preseed"],
    },
    {
        "id": "debian-13.3-netboot",
        "channel": "stable",
        "kind": "installer_bootstrap",
        "version": "13.3.0",
        "name": "Debian 13.3 Netboot Installer Files",
        "description": (
            "Small Debian installer bootstrap: linux + initrd.gz " "for Netboot and Preseed."
        ),
        "size_est": "~45 MB",
        "dest_folder": "debian-13.3",
        "kernel_url": "https://deb.debian.org/debian/dists/trixie/main/installer-amd64/current/images/netboot/debian-installer/amd64/linux",
        "initrd_url": "https://deb.debian.org/debian/dists/trixie/main/installer-amd64/current/images/netboot/debian-installer/amd64/initrd.gz",
        "files": {"kernel": "linux", "initrd": "initrd.gz"},
        "boot_targets": ["Debian Netboot", "Debian Preseed"],
    },
    {
        "id": "debian-13.3-netinst-iso",
        "channel": "stable",
        "kind": "installer_iso",
        "version": "13.3.0",
        "name": "Debian 13.3 Netinst ISO",
        "description": (
            "Official small installation ISO. " "Extracts into installer assets and keeps the ISO."
        ),
        "size_est": "~700 MB",
        "dest_folder": "debian-13.3-netinst",
        "iso_url": "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-13.3.0-amd64-netinst.iso",
        "files": {"iso": "debian-13.3.0-amd64-netinst.iso"},
        "iso_only": True,
        "boot_targets": ["Debian Netboot", "Debian Preseed"],
    },
    {
        "id": "debian-13.3-live-xfce",
        "channel": "stable",
        "kind": "live_iso",
        "version": "13.3.0",
        "name": "Debian 13.3 Live Xfce ISO",
        "description": (
            "Official Debian Live image with Calamares installer. " "Experimental in iPXE Station."
        ),
        "size_est": "~3.0 GB",
        "dest_folder": "debian-13.3-live-xfce",
        "iso_url": "https://cdimage.debian.org/debian-cd/current-live/amd64/iso-hybrid/debian-live-13.3.0-amd64-xfce.iso",
        "files": {"iso": "debian-live-13.3.0-amd64-xfce.iso"},
        "iso_only": True,
        "experimental": True,
        "boot_targets": ["Debian Live (Experimental)"],
    },
    {
        "id": "debian-13.3-live-gnome",
        "channel": "stable",
        "kind": "live_iso",
        "version": "13.3.0",
        "name": "Debian 13.3 Live GNOME ISO",
        "description": "Official Debian Live GNOME image. Experimental in iPXE Station.",
        "size_est": "~4.0 GB",
        "dest_folder": "debian-13.3-live-gnome",
        "iso_url": "https://cdimage.debian.org/debian-cd/current-live/amd64/iso-hybrid/debian-live-13.3.0-amd64-gnome.iso",
        "files": {"iso": "debian-live-13.3.0-amd64-gnome.iso"},
        "iso_only": True,
        "experimental": True,
        "boot_targets": ["Debian Live (Experimental)"],
    },
]

SYSTEM_PRESETS_SEED = [
    {
        "id": "acquire_ubuntu",
        "name": "Ubuntu",
        "category": "linux",
        "mode": "acquire",
        "section": "ubuntu",
        "enabled": True,
        "order": 10,
        "source": "system",
    },
    {
        "id": "acquire_debian",
        "name": "Debian",
        "category": "linux",
        "mode": "acquire",
        "section": "debian",
        "enabled": True,
        "order": 20,
        "source": "system",
    },
    {
        "id": "acquire_tools",
        "name": "Tools",
        "category": "utility",
        "mode": "acquire",
        "section": "tools",
        "enabled": True,
        "order": 30,
        "source": "system",
    },
    {
        "id": "acquire_antivirus",
        "name": "Antivirus",
        "category": "security",
        "mode": "acquire",
        "section": "antivirus",
        "enabled": True,
        "order": 40,
        "source": "system",
    },
]

PRESETS_DIR = IPXE_ROOT / "presets"
SYSTEM_PRESETS_FILE = PRESETS_DIR / "system_presets.json"
USER_PRESETS_FILE = PRESETS_DIR / "user_presets.json"
ASSET_LABELS_FILE = PRESETS_DIR / "asset_labels.json"


class PresetModel(BaseModel):
    id: str
    name: str
    category: str = "custom"
    mode: str = "acquire"
    section: str = ""
    enabled: bool = True
    order: int = 100
    source: str = "user"
    method: str = ""
    description: str = ""
    params: dict = {}


class PresetCreateRequest(BaseModel):
    name: str
    id: str = ""
    category: str = "custom"
    mode: str = "acquire"
    section: str = ""
    enabled: bool = True
    order: int = 100
    method: str = ""
    description: str = ""
    params: dict = {}


class PresetUpdateRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    mode: str | None = None
    section: str | None = None
    enabled: bool | None = None
    order: int | None = None
    method: str | None = None
    description: str | None = None
    params: dict | None = None


def _slugify_preset_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "preset"


def _ensure_preset_store() -> None:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    if not SYSTEM_PRESETS_FILE.exists():
        SYSTEM_PRESETS_FILE.write_text(json.dumps(SYSTEM_PRESETS_SEED, indent=2))
    else:
        existing = _load_preset_file(SYSTEM_PRESETS_FILE, [])
        by_id = {item.get("id"): item for item in existing if isinstance(item, dict)}
        changed = False
        for seed in SYSTEM_PRESETS_SEED:
            if seed["id"] not in by_id:
                existing.append(seed)
                changed = True
        if changed:
            SYSTEM_PRESETS_FILE.write_text(json.dumps(existing, indent=2))
    if not USER_PRESETS_FILE.exists():
        USER_PRESETS_FILE.write_text("[]")


def _load_preset_file(path: Path, fallback: list[dict]) -> list[dict]:
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return fallback
    if not isinstance(raw, list):
        return fallback
    items = []
    for item in raw:
        if isinstance(item, dict):
            items.append(item)
    return items


def _load_merged_presets() -> list[dict]:
    _ensure_preset_store()
    system = _load_preset_file(SYSTEM_PRESETS_FILE, SYSTEM_PRESETS_SEED)
    users = _load_preset_file(USER_PRESETS_FILE, [])
    merged = [PresetModel(**p).model_dump() for p in system] + [
        PresetModel(**p).model_dump() for p in users
    ]
    merged.sort(key=lambda p: (p.get("order", 100), p.get("name", "").lower()))
    return merged


def _load_user_presets() -> list[dict]:
    _ensure_preset_store()
    return [PresetModel(**p).model_dump() for p in _load_preset_file(USER_PRESETS_FILE, [])]


def _save_user_presets(items: list[dict]) -> None:
    USER_PRESETS_FILE.write_text(json.dumps(items, indent=2))


def _load_asset_labels() -> dict[str, str]:
    _ensure_preset_store()
    if not ASSET_LABELS_FILE.exists():
        return {}
    try:
        raw = json.loads(ASSET_LABELS_FILE.read_text())
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    labels: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        normalized_key = key.strip().lstrip("/")
        normalized_value = value.strip().lower()
        if not normalized_key or not normalized_value:
            continue
        labels[normalized_key] = normalized_value
    return labels


def _save_asset_labels(labels: dict[str, str]) -> None:
    _ensure_preset_store()
    ASSET_LABELS_FILE.write_text(json.dumps(labels, indent=2, sort_keys=True))


def _set_asset_label(path_in_http: str, category: str) -> None:
    key = path_in_http.strip().lstrip("/")
    cat = category.strip().lower()
    if not key:
        return
    labels = _load_asset_labels()
    if cat:
        labels[key] = cat
    else:
        labels.pop(key, None)
    _save_asset_labels(labels)


def _prune_asset_labels(existing_http_files: list[str]) -> dict[str, str]:
    labels = _load_asset_labels()
    existing = set(existing_http_files)
    pruned = {k: v for k, v in labels.items() if k in existing}
    if pruned != labels:
        _save_asset_labels(pruned)
    return pruned


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


def _check_disk_space(path: Path, required_bytes: int, label: str) -> None:
    """Raise HTTPException 507 if free disk space is below required_bytes."""
    free = shutil.disk_usage(path).free
    if free < required_bytes:
        free_gb = free / (1024**3)
        need_gb = required_bytes / (1024**3)
        raise HTTPException(
            status_code=507,
            detail=(
                f"Insufficient disk space for {label}: "
                f"{free_gb:.1f} GB free, need ~{need_gb:.1f} GB"
            ),
        )


def _extract_full_iso(iso_path: Path, dest_dir: Path) -> dict:
    """Helper function to extract entire ISO contents to destination directory."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Require 1.5× ISO size free — extracted tree is roughly equal to the ISO
        # and 7z needs temporary space during extraction.
        try:
            _check_disk_space(dest_dir, int(iso_path.stat().st_size * 1.5), "ISO extraction")
        except HTTPException as exc:
            return {"success": False, "error": exc.detail}

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

    http_files = _list_relative_files(HTTP_ROOT, max_depth=3)
    return {
        "http": http_files,
        "tftp": _list_relative_files(TFTP_ROOT, max_depth=3),
        "ipxe": _list_relative_files(IPXE_ROOT, max_depth=3),
        "asset_labels": _prune_asset_labels(http_files),
    }


@assets_router.get("/catalog")
def assets_catalog():
    """Return discovered distro assets by version."""
    ubuntu = _scan_distro_versions("ubuntu", HTTP_ROOT)
    debian = _scan_distro_versions("debian", HTTP_ROOT)
    windows = _scan_distro_versions("windows", HTTP_ROOT)
    rescue = _scan_distro_versions("rescue", HTTP_ROOT)
    kaspersky = _scan_distro_versions("kaspersky", HTTP_ROOT)
    hiren = _scan_distro_versions("hiren", HTTP_ROOT)

    return {
        "ubuntu": ubuntu,
        "debian": debian,
        "windows": windows,
        "rescue": rescue,
        "kaspersky": kaspersky,
        "hiren": hiren,
    }


@assets_router.get("/wimboot-status")
def wimboot_status():
    """Return wimboot binary presence and WinPE file status."""
    wimboot_path = HTTP_ROOT / "wimboot"
    winpe_dir = HTTP_ROOT / "winpe"
    return {
        "wimboot_present": wimboot_path.exists(),
        "wimboot_size": wimboot_path.stat().st_size if wimboot_path.exists() else None,
        "winpe_files": {
            "BCD": (winpe_dir / "Boot" / "BCD").exists(),
            "boot_sdi": (winpe_dir / "Boot" / "boot.sdi").exists(),
            "boot_wim": (winpe_dir / "sources" / "boot.wim").exists(),
        },
    }


@assets_router.get("/presets")
def list_presets():
    """Return merged preset catalog (system + user)."""
    return {"presets": _load_merged_presets()}


@assets_router.post("/presets")
def create_preset(payload: PresetCreateRequest):
    """Create a user preset in catalog."""
    _ensure_preset_store()
    merged = _load_merged_presets()
    preset_id = payload.id.strip() or _slugify_preset_id(payload.name)
    if any(p["id"] == preset_id for p in merged):
        raise HTTPException(status_code=409, detail=f"Preset '{preset_id}' already exists")

    user_items = _load_preset_file(USER_PRESETS_FILE, [])
    new_item = PresetModel(
        id=preset_id,
        name=payload.name,
        category=payload.category,
        mode=payload.mode,
        section=payload.section,
        enabled=payload.enabled,
        order=payload.order,
        source="user",
        method=payload.method,
        description=payload.description,
        params=payload.params,
    ).model_dump()
    user_items.append(new_item)
    _save_user_presets(user_items)
    return {"success": True, "preset": new_item}


@assets_router.patch("/presets/{preset_id}")
def update_preset(preset_id: str, payload: PresetUpdateRequest):
    """Update a user preset."""
    user_items = _load_user_presets()
    idx = next((i for i, item in enumerate(user_items) if item.get("id") == preset_id), None)
    if idx is None:
        if any(item.get("id") == preset_id for item in _load_merged_presets()):
            raise HTTPException(status_code=403, detail="System presets are read-only")
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")

    updated = {**user_items[idx]}
    patch = payload.model_dump(exclude_unset=True, exclude_none=True)
    updated.update(patch)
    updated["id"] = preset_id
    updated["source"] = "user"
    user_items[idx] = PresetModel(**updated).model_dump()
    _save_user_presets(user_items)
    return {"success": True, "preset": user_items[idx]}


@assets_router.delete("/presets/{preset_id}")
def delete_preset(preset_id: str):
    """Delete a user preset."""
    user_items = _load_user_presets()
    filtered = [item for item in user_items if item.get("id") != preset_id]
    if len(filtered) == len(user_items):
        if any(item.get("id") == preset_id for item in _load_merged_presets()):
            raise HTTPException(status_code=403, detail="System presets are read-only")
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")
    _save_user_presets(filtered)
    return {"success": True}


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
def assets_boot_recipe(version_path: str, scenario: str, preseed_profile: str | None = None):
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

    if preseed_profile:
        entry = {**entry, "preseed_profile": preseed_profile}

    return get_recipe(scenario, entry, s.server_ip, s.http_port, nfs_root=nfs_root)


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
    tmp_target = target.with_suffix(target.suffix + ".tmp")

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
            with open(tmp_target, "wb") as fh:
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

        # Atomically move completed download to final path
        tmp_target.replace(target)

        with download_progress_lock:
            download_progress[progress_key] = {
                "downloaded": downloaded,
                "total": total_size,
                "percentage": 100,
                "status": "complete",
                "completed_at": time.time(),
            }

        add_log("download", "info", f"Completed downloading {progress_key} ({downloaded} bytes)")

        auto_extract = load_settings().auto_extraction
        if auto_extract and target.suffix.lower() == ".iso":
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
        tmp_target.unlink(missing_ok=True)
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
async def upload_asset(request: Request, file: UploadFile = File(...), dest: str = ""):
    """Upload a file into /srv/http/<dest> (relative), streamed in chunks."""
    form = await request.form()
    form_dest = str(form.get("dest") or "").strip()
    form_category = str(form.get("category") or "").strip().lower()
    effective_dest = form_dest or dest

    target_dir = _resolve_within_root(
        HTTP_ROOT, effective_dest, allow_empty=True, path_label="dest"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    _check_disk_space(target_dir, 200 * 1024 * 1024, "upload")  # require 200 MB free minimum
    safe_filename = _validate_filename(file.filename)
    target_path = _resolve_within_root(target_dir, safe_filename, path_label="filename")
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    try:
        with open(tmp_path, "wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                fh.write(chunk)
        tmp_path.replace(target_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")
    saved = str(target_path.relative_to(HTTP_ROOT))
    _set_asset_label(saved, form_category)
    return {"saved": saved, "category": form_category}


@assets_router.delete("/file")
def delete_asset_file(path: str, recursive: bool = False):
    """Delete a file (or directory with recursive=true) under /srv/http."""
    rel_path = (path or "").strip().lstrip("/")
    if not rel_path:
        raise HTTPException(status_code=400, detail="path is required")

    target = _resolve_within_root(HTTP_ROOT, rel_path, path_label="path")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {rel_path}")

    if target.is_dir():
        if not recursive:
            raise HTTPException(
                status_code=400,
                detail=("Path is a directory. Pass recursive=true to delete directories."),
            )
        shutil.rmtree(target)
        deleted_kind = "directory"
    else:
        target.unlink()
        deleted_kind = "file"

    # Keep labels storage in sync.
    labels = _load_asset_labels()
    prefix = f"{rel_path.rstrip('/')}/"
    to_delete = [k for k in labels if k == rel_path or k.startswith(prefix)]
    for key in to_delete:
        labels.pop(key, None)
    _save_asset_labels(labels)

    add_log("assets", "info", f"Deleted {deleted_kind}: {rel_path}")
    return {"success": True, "deleted": rel_path, "kind": deleted_kind}


@assets_router.post("/extract-iso")
def extract_iso(request: ExtractISORequest):
    """Extract kernel and initrd from an ISO file using 7zip."""
    iso_file = _resolve_within_root(HTTP_ROOT, request.iso_path, path_label="iso_path")
    if not iso_file.exists():
        raise HTTPException(status_code=404, detail=f"ISO file not found: {request.iso_path}")

    # kernel + initrd are typically < 500 MB total; require that as a minimum safety margin
    _check_disk_space(HTTP_ROOT, 500 * 1024 * 1024, "ISO extraction")

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


@assets_router.get("/versions/debian")
def get_debian_versions():
    """Return backend-owned Debian download products."""
    return {"products": DEBIAN_PRODUCTS}


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


@assets_router.get("/versions/hiren")
def get_hiren_versions():
    """Return available modern Hiren's BootCD PE version metadata.

    The ISO filename is typically stable (HBCD_PE_x64.iso), while the version
    is published on the download page.
    """
    import re
    from urllib.parse import urljoin

    from bs4 import BeautifulSoup

    fallback = {
        "version": "1.0.8",
        "name": "Hiren's BootCD PE v1.0.8",
        "iso_url": "https://www.hirensbootcd.org/files/HBCD_PE_x64.iso",
        "iso_name": "HBCD_PE_x64.iso",
        "dest_folder": "hiren-1.0.8",
        "size_est": "~3.5 GB",
        "notes": "Modern PE build (Windows-based).",
    }

    try:
        page_url = "https://www.hirensbootcd.org/download/"
        response = requests.get(page_url, timeout=12)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        iso_url = fallback["iso_url"]
        for link in soup.find_all("a", href=True):
            href = (link.get("href") or "").strip()
            if "HBCD_PE_x64.iso" in href:
                iso_url = urljoin(page_url, href)
                break

        text = soup.get_text(" ", strip=True)
        m = re.search(r"\b(?:version|v)\s*[:=]?\s*(\d+\.\d+\.\d+)\b", text, re.IGNORECASE)
        version = m.group(1) if m else fallback["version"]

        entry = {
            "version": version,
            "name": f"Hiren's BootCD PE v{version}",
            "iso_url": iso_url,
            "iso_name": "HBCD_PE_x64.iso",
            "dest_folder": f"hiren-{version}",
            "size_est": "~3.5 GB",
            "notes": "Modern PE build (Windows-based).",
        }
        return {"versions": [entry]}
    except Exception as exc:
        add_log("system", "warning", f"Hiren versions fetch failed, using fallback: {exc}")
        return {"versions": [fallback]}


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


@assets_router.get("/versions/ubuntu/desktop")
def get_ubuntu_desktop_versions():
    """Fetch available Ubuntu Desktop ISO versions from releases.ubuntu.com."""
    import re

    try:
        main_url = "https://releases.ubuntu.com/"
        resp = requests.get(main_url, timeout=10)
        resp.raise_for_status()

        major_versions = re.findall(r'href="(\d+\.04)/"', resp.text)
        active = sorted({v for v in major_versions if float(v) >= 20.04}, reverse=True)

        result = []
        for major_ver in active[:6]:
            try:
                dir_resp = requests.get(f"{main_url}{major_ver}/", timeout=10)
                dir_resp.raise_for_status()

                desktop_isos = sorted(
                    set(re.findall(r"ubuntu-[\d.]+-desktop-amd64\.iso", dir_resp.text)),
                    key=lambda x: [int(n) for n in re.findall(r"\d+", x)],
                    reverse=True,
                )
                if not desktop_isos:
                    continue

                latest = desktop_isos[0]
                m = re.search(r"ubuntu-([\d.]+)-desktop", latest)
                full_ver = m.group(1) if m else major_ver
                result.append(
                    {
                        "version": major_ver,
                        "full_version": full_ver,
                        "name": f"Ubuntu {full_ver} LTS Desktop",
                        "iso_name": latest,
                        "iso_url": f"{main_url}{major_ver}/{latest}",
                        "dest_folder": f"ubuntu-{major_ver}-desktop",
                        "size_est": "~5–6 GB",
                    }
                )
            except Exception:
                continue

        return {"versions": result}

    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch Ubuntu Desktop versions: {exc}"
        )


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
    """Check if a remote URL is accessible.

    Some mirrors/CDNs reject ``HEAD`` while allowing ``GET`` (common on
    redirect/download endpoints). We probe with HEAD first, then fall back to
    a lightweight streamed GET when needed.
    """
    headers = {
        "User-Agent": "iPXE-Station/1.0 (+https://github.com/loglux/ipxe-station)",
        "Accept": "*/*",
    }

    def _response_payload(resp: requests.Response) -> dict:
        size = resp.headers.get("content-length")
        return {
            "ok": 200 <= resp.status_code < 400,
            "status": resp.status_code,
            "size": int(size) if size and size.isdigit() else None,
        }

    try:
        r = requests.head(url, allow_redirects=True, timeout=10, headers=headers)
        payload = _response_payload(r)

        if payload["ok"]:
            return payload

        # Fallback for hosts that disallow/limit HEAD but allow GET.
        if r.status_code in {403, 405, 406, 429, 500, 502, 503, 504}:
            rg = requests.get(
                url,
                allow_redirects=True,
                timeout=10,
                headers=headers,
                stream=True,
            )
            try:
                return _response_payload(rg)
            finally:
                rg.close()

        return payload
    except Exception as exc:
        return {"ok": False, "status": None, "size": None, "error": str(exc)}

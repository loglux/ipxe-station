"""Keeping a Kaspersky Rescue Disk (KRD) folder current, and giving it the firmware it lacks.

Two independent jobs on the extracted disk that is booted over NFS or HTTP (the firmware half is in
krd_firmware.py):

* **Antivirus databases.** KRD keeps them in one squashfs module, ``live/KRD/30-bases.srm``.
  Kaspersky publishes a fresh one (``42-freshbases.srm``) with its SHA-512 in ``hashes.txt``;
  replacing the module is what KRD's own updater does and what makes it report
  "Databases are up to date".
* **Firmware.** The disk carries almost no firmware, so Wi-Fi and Bluetooth of many laptops stay
  dead (KRD then shows "Some hardware does not work correctly"). Its boot hook unpacks one
  ``linux-firmware-*.tar.gz`` from the disk root, which may be the full 436 MB release or a small
  archive with only the files a fleet needs.
"""

import hashlib
import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

BASES_URL = "https://rescuedisk.s.kaspersky-labs.com/updatable/2024/bases/"
BASES_MODULE = "live/KRD/30-bases.srm"
FRESH_MODULE_NAME = "42-freshbases.srm"
TIMESTAMP_FILE = "krd_bases_timestamp.txt"
VERSION_FILE = "krd_version.txt"
CHECKSUM_FILE = "sha256sum.txt"
MIN_FREE_BYTES = 400 * 1024 * 1024
KEEP_BACKUPS = 3

_FOLDER_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_SHA512 = re.compile(r"^([0-9a-fA-F]{128})\s+\*?(?:\./)?(\S+)\s*$")


class KrdError(Exception):
    """A problem worth showing to the person who pressed the button."""


# ---------------------------------------------------------------------------
# Finding the disk
# ---------------------------------------------------------------------------


def find_krd_folders(http_root: Path) -> List[Path]:
    """Folders under the web root that hold an extracted Kaspersky Rescue Disk."""
    try:
        candidates = sorted(p for p in http_root.iterdir() if p.is_dir())
    except OSError:
        return []
    return [p for p in candidates if (p / BASES_MODULE).is_file()]


def resolve_folder(http_root: Path, name: str) -> Path:
    if not _FOLDER_NAME.match(name or ""):
        raise KrdError("Invalid folder name")
    for folder in find_krd_folders(http_root):
        if folder.name == name:
            return folder
    raise KrdError(f"'{name}' is not an extracted Kaspersky Rescue Disk")


def _read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def local_bases_timestamp(folder: Path) -> str:
    return _read_text(folder / TIMESTAMP_FILE)


def krd_version(folder: Path) -> str:
    return _read_text(folder / VERSION_FILE)


# ---------------------------------------------------------------------------
# Antivirus databases
# ---------------------------------------------------------------------------

_XML_TIMESTAMP = re.compile(r'databases_timestamp\s*=\s*"(\d+)"')
_XML_VERSION = re.compile(r'product_version\s*=\s*"([\d.]+)"')


def remote_bases_info() -> Dict[str, str]:
    """What Kaspersky currently publishes: the databases timestamp and the product version."""
    try:
        response = requests.get(BASES_URL + "krd.xml", timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise KrdError(f"Could not reach the Kaspersky update server: {exc}") from exc
    stamp = _XML_TIMESTAMP.search(response.text)
    if not stamp:
        raise KrdError("The update server answered, but its krd.xml has no databases timestamp")
    version = _XML_VERSION.search(response.text)
    return {"timestamp": stamp.group(1), "product_version": version.group(1) if version else ""}


def format_timestamp(value: str) -> str:
    """202609261328 -> 2026-09-26 13:28 (the raw value if it is not that shape)."""
    if re.fullmatch(r"\d{12}", value or ""):
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]} {value[8:10]}:{value[10:12]}"
    return value or ""


def bases_status(folder: Path) -> dict:
    local = local_bases_timestamp(folder)
    status = {
        "local": local,
        "local_label": format_timestamp(local),
        "remote": "",
        "remote_label": "",
        "up_to_date": None,
        "error": "",
    }
    try:
        remote = remote_bases_info()
    except KrdError as exc:
        status["error"] = str(exc)
        return status
    status["remote"] = remote["timestamp"]
    status["remote_label"] = format_timestamp(remote["timestamp"])
    status["up_to_date"] = bool(local) and local >= remote["timestamp"]
    return status


def _expected_sha512() -> str:
    try:
        response = requests.get(BASES_URL + "hashes.txt", timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise KrdError(f"Could not read the checksum list of the update server: {exc}") from exc
    for line in response.text.splitlines():
        match = _SHA512.match(line.strip())
        if match and match.group(2) == FRESH_MODULE_NAME:
            return match.group(1).lower()
    raise KrdError(f"hashes.txt does not list {FRESH_MODULE_NAME}")


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _replace_checksum_line(sums_file: Path, relative: str, digest: str) -> None:
    """Point the disk's own sha256sum.txt at the new module (it is read by verify-checksums)."""
    try:
        lines = sums_file.read_text().splitlines()
    except OSError:
        return
    target = f"./{relative}"
    changed = False
    for index, line in enumerate(lines):
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].strip() == target:
            lines[index] = f"{digest}  {target}"
            changed = True
    if changed:
        tmp = sums_file.with_name(sums_file.name + ".tmp")
        tmp.write_text("\n".join(lines) + "\n")
        os.replace(tmp, sums_file)


def _backup_bases(folder: Path, backup_root: Path) -> Optional[Path]:
    """Keep the module being replaced (and its timestamp) so the update can be undone."""
    current = folder / BASES_MODULE
    if not current.is_file():
        return None
    stamp = local_bases_timestamp(folder) or time.strftime("%Y%m%d%H%M", time.localtime())
    target = backup_root / f"{folder.name}-bases-{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current, target / current.name)
    for name in (TIMESTAMP_FILE, CHECKSUM_FILE):
        if (folder / name).is_file():
            shutil.copy2(folder / name, target / name)
    kept = sorted(p for p in backup_root.glob(f"{folder.name}-bases-*") if p.is_dir())
    for stale in kept[:-KEEP_BACKUPS]:
        shutil.rmtree(stale, ignore_errors=True)
    return target


def update_bases(
    folder: Path,
    backup_root: Path,
    progress: Optional[Callable[[int, int], None]] = None,
    force: bool = False,
) -> dict:
    """Download the current databases, verify them and swap them in. Returns what happened."""
    remote = remote_bases_info()
    local = local_bases_timestamp(folder)
    if not force and local and local >= remote["timestamp"]:
        return {"updated": False, "timestamp": local, "message": "Databases are already current."}

    expected = _expected_sha512()
    free = shutil.disk_usage(folder).free
    if free < MIN_FREE_BYTES:
        raise KrdError(f"Not enough free disk space: {free // (1024 * 1024)} MB free, need ~400 MB")

    module = folder / BASES_MODULE
    partial = module.with_name(module.name + ".download")
    digest = hashlib.sha512()
    try:
        with requests.get(BASES_URL + FRESH_MODULE_NAME, stream=True, timeout=30) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(partial, "wb") as out:
                for block in response.iter_content(1024 * 1024):
                    out.write(block)
                    digest.update(block)
                    done += len(block)
                    if progress:
                        progress(done, total)
        if digest.hexdigest() != expected:
            raise KrdError(
                "The downloaded databases do not match the published checksum; nothing was changed."
            )
        backup = _backup_bases(folder, backup_root)
        mode = module.stat().st_mode & 0o777 if module.exists() else 0o644
        os.chmod(partial, mode)
        os.replace(partial, module)
    except requests.RequestException as exc:
        raise KrdError(f"Download failed: {exc}") from exc
    finally:
        partial.unlink(missing_ok=True)

    (folder / TIMESTAMP_FILE).write_text(remote["timestamp"] + "\n")
    _replace_checksum_line(folder / CHECKSUM_FILE, BASES_MODULE, _sha256_of(module))
    return {
        "updated": True,
        "timestamp": remote["timestamp"],
        "previous": local,
        "backup": str(backup) if backup else "",
        "message": f"Databases updated to {format_timestamp(remote['timestamp'])}.",
    }


# ---------------------------------------------------------------------------
# Background jobs (downloads take minutes)
# ---------------------------------------------------------------------------

_jobs: Dict[str, dict] = {}
_jobs_lock = threading.Lock()


def job_status(key: str) -> dict:
    with _jobs_lock:
        return dict(_jobs.get(key, {"state": "idle"}))


def start_job(key: str, work: Callable[[Callable[[int, int], None]], dict]) -> bool:
    """Run ``work(progress)`` in a thread; False when a job under this key is already running."""
    with _jobs_lock:
        if _jobs.get(key, {}).get("state") == "running":
            return False
        _jobs[key] = {"state": "running", "done": 0, "total": 0, "started": time.time()}

    def progress(done: int, total: int) -> None:
        with _jobs_lock:
            _jobs[key].update(done=done, total=total)

    def run() -> None:
        try:
            result = work(progress)
            update = {"state": "done", "result": result}
        except KrdError as exc:
            update = {"state": "error", "error": str(exc)}
        except Exception as exc:  # a failed job must not vanish silently
            logger.exception("KRD job %s failed", key)
            update = {"state": "error", "error": f"Unexpected error: {exc}"}
        with _jobs_lock:
            _jobs[key].update(update, finished=time.time())

    threading.Thread(target=run, daemon=True, name=f"krd-{key}").start()
    return True

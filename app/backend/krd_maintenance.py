"""Keeping a Kaspersky Rescue Disk (KRD) folder current, and giving it the firmware it lacks.

Two independent jobs, both working on the extracted disk that is booted over NFS or HTTP:

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
import io
import logging
import os
import re
import shutil
import tarfile
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

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

# The KRD 24 kernel (6.1) asks for API 72 of the Wi-Fi firmware; newer releases of linux-firmware
# dropped the old versions, so both the small and the full archive come from this release.
FIRMWARE_TAG = "20230210"
FIRMWARE_FILE_URL = "https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain/{path}?h={tag}"
FULL_ARCHIVE_URL = "https://mirrors.edge.kernel.org/pub/linux/kernel/firmware/{name}"
FULL_SUMS_URL = "https://mirrors.edge.kernel.org/pub/linux/kernel/firmware/sha256sums.asc"
CUSTOM_ARCHIVE = "linux-firmware-custom.tar.gz"
FULL_ARCHIVE = f"linux-firmware-{FIRMWARE_TAG}.tar.gz"
# kernel.org answers 403 to the default python-requests User-Agent.
HEADERS = {"User-Agent": "ipxe-station"}
MAX_FIRMWARE_FILE_BYTES = 30 * 1024 * 1024
MAX_FIRMWARE_FILES = 60
# KRD skips firmware below this much RAM (the value is in its boot hook, in kB).
FIRMWARE_MIN_RAM_GB = 3.1

_FOLDER_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_FIRMWARE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-/]{0,119}$")
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
# Firmware
# ---------------------------------------------------------------------------

# Firmware for common laptop Wi-Fi and Bluetooth chips, matched to the KRD 24 kernel. A file the
# release does not have is skipped rather than failing the build.
FIRMWARE_PRESETS: List[dict] = [
    {
        "id": "intel-ax211",
        "name": "Intel Wi-Fi 6E AX211 / AX411",
        "description": "Alder and Raptor Lake laptops (e.g. Dell Latitude 5530).",
        "files": ["iwlwifi-so-a0-gf-a0-72.ucode", "iwlwifi-so-a0-gf-a0.pnvm"],
    },
    {
        "id": "intel-ax201",
        "name": "Intel Wi-Fi 6 AX200 / AX201",
        "description": "Comet, Ice, Tiger and Alder Lake laptops.",
        "files": [
            "iwlwifi-cc-a0-72.ucode",
            "iwlwifi-QuZ-a0-hr-b0-72.ucode",
            "iwlwifi-Qu-c0-hr-b0-72.ucode",
            "iwlwifi-so-a0-hr-b0-72.ucode",
        ],
    },
    {
        "id": "intel-ax210",
        "name": "Intel Wi-Fi 6E AX210",
        "description": "Add-in Wi-Fi 6E cards.",
        "files": ["iwlwifi-ty-a0-gf-a0-72.ucode", "iwlwifi-ty-a0-gf-a0.pnvm"],
    },
    {
        "id": "intel-bluetooth",
        "name": "Intel Bluetooth",
        "description": "Bluetooth of the Intel Wi-Fi cards above.",
        "files": [
            "intel/ibt-0040-0041.sfi",
            "intel/ibt-0040-0041.ddc",
            "intel/ibt-0040-4150.sfi",
            "intel/ibt-0040-4150.ddc",
            "intel/ibt-19-0-4.sfi",
            "intel/ibt-19-0-4.ddc",
            "intel/ibt-19-16-4.sfi",
            "intel/ibt-19-16-4.ddc",
            "intel/ibt-19-32-4.sfi",
            "intel/ibt-19-32-4.ddc",
        ],
    },
]

_LOAD_FAILED = re.compile(
    r"(?:firmware: failed to load|Direct firmware load for|Failed to load (?:Intel )?firmware file)"
    r"\s+(\S+)"
)
_NUMBERED = re.compile(r"^(?P<stem>.+)-(?P<num>\d+)\.(?P<ext>ucode|fw|bin)$")


def valid_firmware_name(name: str) -> bool:
    return bool(_FIRMWARE_NAME.match(name or "")) and ".." not in name.split("/")


def _companions(name: str) -> List[str]:
    """Files that go with a firmware file but that the kernel does not report as missing."""
    extras: List[str] = []
    numbered = _NUMBERED.match(name)
    if numbered and name.startswith("iwlwifi-") and "-gf-" in name:
        extras.append(f"{numbered.group('stem')}.pnvm")
    if name.startswith("intel/ibt-") and name.endswith(".sfi"):
        extras.append(name[: -len(".sfi")] + ".ddc")
    return extras


def parse_missing_firmware(text: str) -> List[dict]:
    """Which firmware files the kernel could not find, from ``dmesg`` output.

    The Wi-Fi driver tries every API version from the newest downwards, so dozens of lines name
    one chip; they are folded into one entry (the newest version, the others as alternatives).
    """
    names: List[str] = []
    for match in _LOAD_FAILED.finditer(text or ""):
        name = match.group(1).rstrip(",.;")
        if name.startswith("(") or not valid_firmware_name(name):
            continue
        if name not in names:
            names.append(name)

    groups: Dict[Tuple[str, str], List[Tuple[int, str]]] = {}
    plain: List[str] = []
    for name in names:
        numbered = _NUMBERED.match(name)
        if numbered:
            key = (numbered.group("stem"), numbered.group("ext"))
            groups.setdefault(key, []).append((int(numbered.group("num")), name))
        else:
            plain.append(name)

    found: List[dict] = []
    for members in groups.values():
        ordered = [n for _, n in sorted(members, reverse=True)]
        found.append({"name": ordered[0], "alternatives": ordered[1:]})
    found.extend({"name": n, "alternatives": []} for n in plain)
    for item in found:
        item["companions"] = _companions(item["name"])
    return found


def presets_covering(names: Iterable[str]) -> List[str]:
    wanted = set(names)
    return [p["id"] for p in FIRMWARE_PRESETS if wanted & set(p["files"])]


def _fetch_firmware_file(path: str, tag: str) -> Optional[bytes]:
    """One file from the linux-firmware release, or None when the release has no such file."""
    url = FIRMWARE_FILE_URL.format(path=path, tag=tag)
    try:
        with requests.get(url, stream=True, timeout=30, headers=HEADERS) as response:
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = bytearray()
            for block in response.iter_content(256 * 1024):
                data.extend(block)
                if len(data) > MAX_FIRMWARE_FILE_BYTES:
                    raise KrdError(f"{path} is unexpectedly large; not adding it")
            return bytes(data)
    except requests.RequestException as exc:
        raise KrdError(f"Could not download {path}: {exc}") from exc


_INSTALLER = """#!/bin/sh
# Copies the bundled firmware into the directory given as the first argument.
# Called by the Kaspersky Rescue Disk boot hook in place of the stock copy-firmware.sh.
dest="$1"
[ -n "$dest" ] || exit 1
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here/files" || exit 1
find . -type f | while read -r file; do
    mkdir -p "$dest/$(dirname "$file")"
    cp "$file" "$dest/$file"
done
"""


def firmware_archives(folder: Path) -> List[Path]:
    return sorted(folder.glob("linux-firmware-*.tar.gz"))


def firmware_state(folder: Path) -> dict:
    archives = firmware_archives(folder)
    return {
        "archives": [{"name": a.name, "size": a.stat().st_size} for a in archives],
        "kind": (
            "custom"
            if [a.name for a in archives] == [CUSTOM_ARCHIVE]
            else "full" if archives else "none"
        ),
        "tag": FIRMWARE_TAG,
        "min_ram_gb": FIRMWARE_MIN_RAM_GB,
    }


def _remove_archives(folder: Path) -> List[str]:
    """KRD refuses to boot when the disk holds more than one linux-firmware archive."""
    removed = []
    for archive in firmware_archives(folder):
        archive.unlink()
        removed.append(archive.name)
    return removed


def build_custom_firmware(
    folder: Path,
    preset_ids: Iterable[str] = (),
    files: Iterable[dict] = (),
    tag: str = FIRMWARE_TAG,
) -> dict:
    """Make ``linux-firmware-custom.tar.gz`` from presets and named files.

    ``files`` are ``{"name": ..., "alternatives": [...]}``; the first candidate that exists in the
    release is taken. Companions (PNVM, DDC) are added when the release has them.
    """
    if not re.fullmatch(r"[0-9A-Za-z._-]{1,40}", tag):
        raise KrdError("Invalid firmware release")
    wanted: List[Tuple[str, List[str], bool]] = []  # (name, alternatives, must exist)
    known = {p["id"]: p for p in FIRMWARE_PRESETS}
    for preset_id in preset_ids:
        if preset_id not in known:
            raise KrdError(f"Unknown firmware preset '{preset_id}'")
        wanted.extend((name, [], False) for name in known[preset_id]["files"])
    for item in files:
        name = str(item.get("name", "")).strip()
        alternatives = [str(a).strip() for a in item.get("alternatives", [])]
        for candidate in [name, *alternatives]:
            if not valid_firmware_name(candidate):
                raise KrdError(f"'{candidate}' is not a valid firmware file name")
        wanted.append((name, alternatives, True))
        wanted.extend((extra, [], False) for extra in _companions(name))

    if not wanted:
        raise KrdError("Choose at least one device or name a firmware file")
    if len(wanted) > MAX_FIRMWARE_FILES:
        raise KrdError(f"Too many files (limit {MAX_FIRMWARE_FILES})")

    added: List[str] = []
    skipped: List[str] = []
    payload: Dict[str, bytes] = {}
    for name, alternatives, _required in wanted:
        if name in payload:
            continue
        data = None
        used = name
        for candidate in [name, *alternatives]:
            data = _fetch_firmware_file(candidate, tag)
            if data is not None:
                used = candidate
                break
        if data is None:
            skipped.append(name)
            continue
        payload[used] = data
        added.append(used)

    if not payload:
        raise KrdError(f"None of the requested files exist in linux-firmware {tag}")

    root = "linux-firmware-custom"
    with tempfile.NamedTemporaryFile(dir=folder, suffix=".tmp", delete=False) as handle:
        tmp = Path(handle.name)
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            installer = _INSTALLER.encode()
            info = tarfile.TarInfo(f"{root}/copy-firmware.sh")
            info.size, info.mode = len(installer), 0o755
            tar.addfile(info, io.BytesIO(installer))
            for name, data in payload.items():
                info = tarfile.TarInfo(f"{root}/files/{name}")
                info.size, info.mode = len(data), 0o644
                tar.addfile(info, io.BytesIO(data))
        replaced = _remove_archives(folder)
        os.chmod(tmp, 0o644)
        os.replace(tmp, folder / CUSTOM_ARCHIVE)
    finally:
        tmp.unlink(missing_ok=True)

    return {
        "archive": CUSTOM_ARCHIVE,
        "size": (folder / CUSTOM_ARCHIVE).stat().st_size,
        "added": added,
        "skipped": skipped,
        "replaced": [r for r in replaced if r != CUSTOM_ARCHIVE],
        "tag": tag,
    }


def _published_sha256(name: str) -> str:
    try:
        response = requests.get(FULL_SUMS_URL, timeout=30, headers=HEADERS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise KrdError(f"Could not read the checksum list of kernel.org: {exc}") from exc
    for line in response.text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == name and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            return parts[0]
    raise KrdError(f"kernel.org publishes no checksum for {name}")


def install_full_firmware(
    folder: Path, progress: Optional[Callable[[int, int], None]] = None
) -> dict:
    """Download the complete linux-firmware release matching the KRD kernel and verify it."""
    expected = _published_sha256(FULL_ARCHIVE)
    free = shutil.disk_usage(folder).free
    if free < 1024 * 1024 * 1024:
        raise KrdError(f"Not enough free disk space: {free // (1024 * 1024)} MB free, need ~1 GB")
    partial = folder / (FULL_ARCHIVE + ".download")
    digest = hashlib.sha256()
    try:
        with requests.get(
            FULL_ARCHIVE_URL.format(name=FULL_ARCHIVE), stream=True, timeout=30, headers=HEADERS
        ) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            with open(partial, "wb") as out:
                for block in r.iter_content(1024 * 1024):
                    out.write(block)
                    digest.update(block)
                    done += len(block)
                    if progress:
                        progress(done, total)
        if digest.hexdigest() != expected:
            raise KrdError("The download does not match kernel.org's checksum; it was discarded.")
        replaced = _remove_archives(folder)
        os.chmod(partial, 0o644)
        os.replace(partial, folder / FULL_ARCHIVE)
    except requests.RequestException as exc:
        raise KrdError(f"Download failed: {exc}") from exc
    finally:
        partial.unlink(missing_ok=True)
    return {
        "archive": FULL_ARCHIVE,
        "size": (folder / FULL_ARCHIVE).stat().st_size,
        "replaced": replaced,
        "tag": FIRMWARE_TAG,
    }


def remove_firmware(folder: Path) -> List[str]:
    return _remove_archives(folder)


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

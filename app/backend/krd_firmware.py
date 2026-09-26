"""Firmware for Kaspersky Rescue Disk: a device catalog and the archive its boot hook reads.

The disk carries almost no firmware, so Wi-Fi, Bluetooth and more stay dead on many laptops. Its
boot hook unpacks exactly one ``linux-firmware-*.tar.gz`` from the disk root, which may be the full
release or a small archive of chosen files (it runs the archive's own ``copy-firmware.sh``).

The official release is downloaded once to a cache on the server (never served to clients) and
checked against kernel.org's checksum. Its ``WHENCE`` file says which files belong to which device,
which gives the catalog; small archives and the full set are then made from the cache.
"""

import fnmatch
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Set, Tuple

import requests

from .krd_maintenance import KrdError

# The KRD 24 kernel (6.1) asks for API 72 of the Wi-Fi firmware; newer releases of linux-firmware
# dropped the old versions, so everything comes from this release.
FIRMWARE_TAG = "20230210"
FIRMWARE_FILE_URL = (
    "https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/"
    "plain/{path}?h={tag}"
)
FULL_ARCHIVE_URL = "https://mirrors.edge.kernel.org/pub/linux/kernel/firmware/{name}"
FULL_SUMS_URL = "https://mirrors.edge.kernel.org/pub/linux/kernel/firmware/sha256sums.asc"
CUSTOM_ARCHIVE = "linux-firmware-custom.tar.gz"
FULL_ARCHIVE = f"linux-firmware-{FIRMWARE_TAG}.tar.gz"
FULL_ARCHIVE_MB = 436
# kernel.org answers 403 to the default python-requests User-Agent.
HEADERS = {"User-Agent": "ipxe-station"}
MAX_FIRMWARE_FILE_BYTES = 30 * 1024 * 1024
MAX_EXTRA_FILES = 60
# KRD skips firmware below this much RAM (the value is in its boot hook, in kB).
FIRMWARE_MIN_RAM_GB = 3.1
# Above this much unpacked firmware a machine needs a lot of RAM to start; the page warns.
LARGE_SELECTION_BYTES = 250 * 1024 * 1024
# A driver with more files than this is split into one entry per chip family.
SPLIT_ABOVE_FILES = 25

CATALOG_FILE = "catalog.json"

_FIRMWARE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-/]{0,119}$")


# ---------------------------------------------------------------------------
# Reading the missing files out of dmesg
# ---------------------------------------------------------------------------

_LOAD_FAILED = re.compile(
    r"(?:firmware: failed to load|Direct firmware load for|Failed to load (?:Intel )?firmware file)"
    r"\s+(\S+)"
)
_NUMBERED = re.compile(r"^(?P<stem>.+)-(?P<num>\d+)\.(?P<ext>ucode|fw|bin)$")


# Files the archive cannot help with. The video driver is in the boot image and starts before the
# archive is unpacked, so it never sees firmware added this way (checked: i915.ko is in KRD 24's
# initrd, iwlwifi and btusb are not).
_NOT_ADDABLE = (
    (
        "i915/",
        "The video driver starts inside the boot image, before the archive is unpacked. Harmless.",
    ),
    ("iwl-debug", "A debug file. Kaspersky ignores it."),
)


def firmware_note(name: str) -> str:
    """Why adding this file to the archive would not help, or an empty string when it would."""
    for prefix, note in _NOT_ADDABLE:
        if name.startswith(prefix):
            return note
    return ""


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
        item["note"] = firmware_note(item["name"])
    return found


# ---------------------------------------------------------------------------
# The downloaded release (cache) and the catalog made from it
# ---------------------------------------------------------------------------


def _paths(cache_root: Path) -> Tuple[Path, Path]:
    return cache_root / FULL_ARCHIVE, cache_root / CATALOG_FILE


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


def _strip_root(name: str) -> str:
    """linux-firmware-20230210/amdgpu/x.bin -> amdgpu/x.bin"""
    _, _, rest = name.partition("/")
    return rest


def _resolve_links(files: Dict[str, int], links: Dict[str, str]) -> Dict[str, str]:
    """Each link path -> the real file it leads to; links that lead nowhere are dropped."""
    resolved: Dict[str, str] = {}
    for path, target in links.items():
        current = path
        for _ in range(8):
            if current in files:
                break
            step = links.get(current)
            if step is None:
                current = ""
                break
            current = posixpath.normpath(posixpath.join(posixpath.dirname(current), step))
        if current in files:
            resolved[path] = current
    return resolved


def _index_tarball(tarball: Path) -> Tuple[Dict[str, int], Dict[str, str], str]:
    """Files with sizes, links with their raw targets, and the WHENCE text of the release."""
    files: Dict[str, int] = {}
    links: Dict[str, str] = {}
    whence = ""
    try:
        with tarfile.open(tarball, "r:gz") as tar:
            for member in tar:
                name = _strip_root(member.name)
                if not name:
                    continue
                if member.isfile():
                    files[name] = member.size
                    if name == "WHENCE":
                        handle = tar.extractfile(member)
                        whence = handle.read().decode("utf-8", errors="replace") if handle else ""
                elif member.issym():
                    links[name] = member.linkname
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise KrdError(f"Could not read the firmware release: {exc}") from exc
    return files, links, whence


def parse_whence(text: str) -> List[dict]:
    """The devices of a WHENCE file: name, description and the files (and links) each one owns."""
    blocks: List[dict] = []
    current: Optional[dict] = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Driver:"):
            spec = line[len("Driver:") :].strip()
            parts = re.split(r"\s+--?\s+", spec, maxsplit=1)
            if len(parts) == 2:
                name, description = parts[0].strip(), parts[1].strip()
            else:
                name, _, description = spec.partition(" ")
            name = name.strip().rstrip(":")
            current = {"name": name, "description": description.strip(), "files": [], "links": []}
            blocks.append(current)
        elif current is not None and line.startswith(("File:", "RawFile:")):
            current["files"].append(line.split(":", 1)[1].strip().strip('"'))
        elif current is not None and line.startswith("Link:") and "->" in line:
            link = line[len("Link:") :].split("->", 1)[0].strip().strip('"')
            current["links"].append(link)
    return blocks


_CATEGORIES = [
    ("bluetooth", ("bluetooth", "btusb", "btintel", "btmtk", "btrtl", "btbcm", "ibt-", "qca/")),
    (
        "wifi",
        (
            "wifi",
            "wireless",
            "wlan",
            "802.11",
            "iwl",
            "ath",
            "rtw",
            "rtl8",
            "brcmfmac",
            "mwifiex",
            "mt76",
            "mt79",
            "wil6210",
            "cypress",
            "wl12",
            "wl18",
        ),
    ),
    (
        "graphics",
        (
            "amdgpu",
            "radeon",
            "i915",
            "nvidia",
            "nouveau",
            "gpu",
            "graphics",
            "video",
            "vega",
            "navi",
            "guc",
            "huc",
        ),
    ),
    ("audio", ("audio", "snd", "sof", "sound", "cs35", "cs42", "tas2")),
    (
        "ethernet",
        (
            "ethernet",
            "bnx",
            "tg3",
            "netronome",
            "mellanox",
            "qed",
            "liquidio",
            "cxgb",
            "e100",
            "rtl_nic",
            "myri",
            "sfc",
            "nic",
        ),
    ),
    ("storage", ("scsi", "fibre", "raid", "qla", "advansys", "nvme")),
]
CATEGORY_LABELS = {
    "wifi": "Wi-Fi",
    "bluetooth": "Bluetooth",
    "graphics": "Graphics",
    "audio": "Audio",
    "ethernet": "Network cards",
    "storage": "Storage",
    "other": "Everything else",
}

# What Intel's chip codes are called on the box.
_IWLWIFI_CHIPS = {
    "so-a0-gf4-a0": "Wi-Fi 7 (Alder/Raptor Lake successor)",
    "so-a0-gf-a0": "Wi-Fi 6E AX211 / AX411 (Alder and Raptor Lake laptops)",
    "so-a0-hr-b0": "Wi-Fi 6 AX201 (Alder Lake laptops)",
    "so-a0-jf-b0": "Wi-Fi 6 (Alder Lake, 9000-series style)",
    "ty-a0-gf-a0": "Wi-Fi 6E AX210 (add-in cards)",
    "ma-b0-gf-a0": "Wi-Fi 6E AX211 (Alder Lake)",
    "ma-b0-hr-b0": "Wi-Fi 6 AX201 (Alder Lake)",
    "gl-c0-fm-c0": "Wi-Fi 7 BE200",
    "cc-a0": "Wi-Fi 6 AX200",
    "QuZ-a0-hr-b0": "Wi-Fi 6 AX201 (Comet Lake laptops)",
    "Qu-c0-hr-b0": "Wi-Fi 6 AX201 (Ice Lake laptops)",
    "Qu-b0-hr-b0": "Wi-Fi 6 AX201",
    "9260-th-b0-jf-b0": "Wireless-AC 9260",
    "9000-pu-b0-jf-b0": "Wireless-AC 9560 / 9462",
    "8265": "Wireless-AC 8265",
    "8000C": "Wireless-AC 8260",
    "7265D": "Wireless-AC 7265",
    "7265": "Wireless-AC 7265",
    "3168": "Wireless-AC 3168",
}


def categorize(name: str, description: str) -> str:
    haystack = f"{name} {description}".lower()
    for category, words in _CATEGORIES:
        if any(word in haystack for word in words):
            return category
    return "other"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def family_key(path: str) -> str:
    """Chip family of a firmware file.

    Files in a nested folder (ath10k/QCA9377/hw1.0/...) belong to their folder. Flat ones are told
    apart by name: the API version and extension are dropped, and so is everything after an
    underscore (amdgpu/navi10_pfp.bin -> amdgpu/navi10).
    """
    directory, _, base = path.rpartition("/")
    if directory.count("/") >= 1:
        return directory
    stem = re.sub(r"-\d{1,3}$", "", base.split(".")[0]).split("_")[0]
    return f"{directory}/{stem}" if directory else stem


def _family_label(driver: str, key: str) -> str:
    """The part of a family key that tells it from its siblings."""
    label = key
    root = driver.lower()
    for prefix in (root + "/", root + "-"):
        if label.lower().startswith(prefix):
            label = label[len(prefix) :]
            break
    label = label.rpartition("/")[2] if "/" in label and label.count("/") == 0 else label
    return label.replace("/", " ") or key


def _family_note(driver: str, key: str) -> str:
    base = key.rpartition("/")[2]
    if driver.lower().startswith("iwlwifi"):
        chip = base.replace("iwlwifi-", "", 1)
        for code, label in _IWLWIFI_CHIPS.items():
            if chip == code or chip.startswith(code):
                return label
    if base.startswith("ibt-"):
        return "Intel Bluetooth"
    return ""


def build_catalog(files: Dict[str, int], links: Dict[str, str], whence: str) -> dict:
    """Devices and the files they need, from a release's file list and its WHENCE."""
    real_link = _resolve_links(files, links)
    known = set(files) | set(real_link)

    merged: Dict[str, dict] = {}
    for block in parse_whence(whence):
        entry = merged.setdefault(
            block["name"].lower(),
            {"name": block["name"], "description": block["description"], "paths": set()},
        )
        if not entry["description"]:
            entry["description"] = block["description"]
        for pattern in block["files"] + block["links"]:
            if any(ch in pattern for ch in "*?["):
                entry["paths"].update(p for p in known if fnmatch.fnmatchcase(p, pattern))
            elif pattern in known:
                entry["paths"].add(pattern)

    def size_of(paths: Iterable[str]) -> int:
        return sum(files.get(p) or files.get(real_link.get(p, ""), 0) for p in paths)

    items: List[dict] = []
    used_ids: Set[str] = set()

    def add(name, description, paths, category):
        base = _slug(name)
        item_id, n = base, 2
        while item_id in used_ids:
            item_id, n = f"{base}-{n}", n + 1
        used_ids.add(item_id)
        ordered = sorted(paths)
        items.append(
            {
                "id": item_id,
                "name": name,
                "description": description,
                "category": category,
                "size": size_of(ordered),
                "count": len(ordered),
                "files": ordered,
            }
        )

    for entry in merged.values():
        paths = sorted(entry["paths"])
        if not paths:
            continue
        category = categorize(entry["name"], entry["description"])
        families: Dict[str, List[str]] = {}
        for path in paths:
            families.setdefault(family_key(path), []).append(path)
        if len(paths) > SPLIT_ABOVE_FILES and len(families) >= 3:
            for key, members in sorted(families.items()):
                label = _family_label(entry["name"], key)
                note = _family_note(entry["name"], key)
                name = f"{note} ({entry['name']} {label})" if note else f"{entry['name']} — {label}"
                add(name, note or entry["description"], members, category)
        else:
            add(entry["name"], entry["description"], paths, category)

    items.sort(key=lambda i: (i["category"] == "other", i["category"], i["name"].lower()))
    return {
        "tag": FIRMWARE_TAG,
        "items": items,
        "links": real_link,
        "all_files": sorted(known),
        "categories": CATEGORY_LABELS,
    }


def load_catalog(cache_root: Path) -> Optional[dict]:
    _, catalog_file = _paths(cache_root)
    try:
        return json.loads(catalog_file.read_text())
    except (OSError, ValueError):
        return None


def source_state(cache_root: Path) -> dict:
    tarball, _ = _paths(cache_root)
    catalog = load_catalog(cache_root) if tarball.exists() else None
    return {
        "tag": FIRMWARE_TAG,
        "download_mb": FULL_ARCHIVE_MB,
        "downloaded": bool(catalog),
        "size": tarball.stat().st_size if tarball.exists() else 0,
        "items": len(catalog["items"]) if catalog else 0,
    }


def catalog_summary(cache_root: Path) -> List[dict]:
    """The catalog as the page shows it (no file lists)."""
    catalog = load_catalog(cache_root)
    if not catalog:
        return []
    return [{k: v for k, v in item.items() if k != "files"} for item in catalog["items"]]


def items_covering(cache_root: Path, names: Iterable[str]) -> List[str]:
    """Catalog entries that hold any of these firmware files."""
    catalog = load_catalog(cache_root)
    wanted = {n for n in names if not firmware_note(n)}
    if not catalog or not wanted:
        return []
    return [i["id"] for i in catalog["items"] if wanted & set(i["files"])]


def download_source(
    cache_root: Path, progress: Optional[Callable[[int, int], None]] = None
) -> dict:
    """Download the official release into the cache, verify it and make the catalog."""
    expected = _published_sha256(FULL_ARCHIVE)
    cache_root.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(cache_root).free
    if free < 1024 * 1024 * 1024:
        raise KrdError(f"Not enough free disk space: {free // (1024 * 1024)} MB free, need ~1 GB")
    tarball, catalog_file = _paths(cache_root)
    partial = tarball.with_name(tarball.name + ".download")
    digest = hashlib.sha256()
    try:
        url = FULL_ARCHIVE_URL.format(name=FULL_ARCHIVE)
        with requests.get(url, stream=True, timeout=30, headers=HEADERS) as response:
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
            raise KrdError("The download does not match kernel.org's checksum; it was discarded.")
        files, links, whence = _index_tarball(partial)
        catalog = build_catalog(files, links, whence)
        if not catalog["items"]:
            raise KrdError("The release has no WHENCE file I can read; it was discarded.")
        os.replace(partial, tarball)
        catalog_file.write_text(json.dumps(catalog))
    except requests.RequestException as exc:
        raise KrdError(f"Download failed: {exc}") from exc
    finally:
        partial.unlink(missing_ok=True)
    return {"items": len(catalog["items"]), "size": tarball.stat().st_size, "tag": FIRMWARE_TAG}


def remove_source(cache_root: Path) -> bool:
    removed = False
    for path in _paths(cache_root):
        if path.exists():
            path.unlink()
            removed = True
    return removed


# ---------------------------------------------------------------------------
# The archive on the disk
# ---------------------------------------------------------------------------

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
    names = [a.name for a in archives]
    return {
        "archives": [{"name": a.name, "size": a.stat().st_size} for a in archives],
        "kind": "custom" if names == [CUSTOM_ARCHIVE] else "full" if archives else "none",
        "tag": FIRMWARE_TAG,
        "min_ram_gb": FIRMWARE_MIN_RAM_GB,
    }


def installed_items(folder: Path, cache_root: Path) -> List[str]:
    """Catalog entries that have any file in the small archive on the disk.

    Building replaces the archive, so the page starts from what is already installed. An entry
    counts if even one of its files is there: an archive made by hand or by an older version may
    hold only part of a chip's files, and dropping the chip on the next build would break it.
    """
    archive = folder / CUSTOM_ARCHIVE
    catalog = load_catalog(cache_root)
    if not archive.exists() or not catalog:
        return []
    try:
        with tarfile.open(archive) as tar:
            names = {n.split("/files/", 1)[1] for n in tar.getnames() if "/files/" in n}
    except (tarfile.TarError, OSError):
        return []
    return [i["id"] for i in catalog["items"] if names & set(i["files"])]


def _remove_archives(folder: Path) -> List[str]:
    """KRD refuses to boot when the disk holds more than one linux-firmware archive."""
    removed = []
    for archive in firmware_archives(folder):
        archive.unlink()
        removed.append(archive.name)
    return removed


def remove_firmware(folder: Path) -> List[str]:
    return _remove_archives(folder)


def _fetch_remote_file(path: str) -> Optional[bytes]:
    """One file from the release on kernel.org, or None when there is no such file."""
    url = FIRMWARE_FILE_URL.format(path=path, tag=FIRMWARE_TAG)
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


def _extras(extra_files: Iterable[dict]) -> List[Tuple[str, List[str], bool]]:
    """Named files as (name, fallbacks, required); companions are added as optional."""
    wanted: List[Tuple[str, List[str], bool]] = []
    for item in extra_files:
        name = str(item.get("name", "")).strip()
        alternatives = [str(a).strip() for a in item.get("alternatives", [])]
        for candidate in [name, *alternatives]:
            if not valid_firmware_name(candidate):
                raise KrdError(f"'{candidate}' is not a valid firmware file name")
        wanted.append((name, alternatives, True))
        wanted.extend((extra, [], False) for extra in _companions(name))
    return wanted


def _write_archive(
    folder: Path, entries: Iterator[Tuple[str, bytes]]
) -> Tuple[List[str], List[str]]:
    """Write linux-firmware-custom.tar.gz from (name, data) pairs; replaces any other archive."""
    root = "linux-firmware-custom"
    added: List[str] = []
    with tempfile.NamedTemporaryFile(dir=folder, suffix=".tmp", delete=False) as handle:
        tmp = Path(handle.name)
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            installer = _INSTALLER.encode()
            info = tarfile.TarInfo(f"{root}/copy-firmware.sh")
            info.size, info.mode = len(installer), 0o755
            tar.addfile(info, io.BytesIO(installer))
            for name, data in entries:
                info = tarfile.TarInfo(f"{root}/files/{name}")
                info.size, info.mode = len(data), 0o644
                tar.addfile(info, io.BytesIO(data))
                added.append(name)
        if not added:
            raise KrdError("Nothing to add: none of the chosen files exist in the release")
        replaced = _remove_archives(folder)
        os.chmod(tmp, 0o644)
        os.replace(tmp, folder / CUSTOM_ARCHIVE)
    finally:
        tmp.unlink(missing_ok=True)
    return added, replaced


def _entries_from_cache(
    tarball: Path, catalog: dict, item_ids: Iterable[str], extras: List[Tuple[str, List[str], bool]]
) -> Tuple[Iterator[Tuple[str, bytes]], List[str]]:
    """Stream the chosen files out of the cached release, one file in memory at a time."""
    links: Dict[str, str] = catalog["links"]
    by_id = {i["id"]: i for i in catalog["items"]}
    unknown = [i for i in item_ids if i not in by_id]
    if unknown:
        raise KrdError(f"Unknown firmware entry '{unknown[0]}'")

    chosen: Set[str] = set()
    for item_id in item_ids:
        chosen.update(by_id[item_id]["files"])

    known = set(catalog["all_files"])
    skipped: List[str] = []
    for name, alternatives, required in extras:
        pick = next((c for c in [name, *alternatives] if c in known or c in links), None)
        if pick:
            chosen.add(pick)
        elif required:
            skipped.append(name)

    # real file in the release -> every name it must appear under (links become copies)
    want: Dict[str, List[str]] = {}
    for path in sorted(chosen):
        want.setdefault(links.get(path, path), []).append(path)

    def stream() -> Iterator[Tuple[str, bytes]]:
        with tarfile.open(tarball, "r:gz") as tar:
            for member in tar:
                names = want.get(_strip_root(member.name))
                if not names or not member.isfile():
                    continue
                handle = tar.extractfile(member)
                data = handle.read() if handle else b""
                for name in names:
                    yield name, data

    return stream(), skipped


def build_custom_firmware(
    folder: Path,
    cache_root: Path,
    item_ids: Iterable[str] = (),
    extra_files: Iterable[dict] = (),
) -> dict:
    """Make ``linux-firmware-custom.tar.gz`` from catalog entries and named files.

    Uses the cached release when there is one. Without it only named files work; they are fetched
    one by one from kernel.org.
    """
    item_ids = list(item_ids)
    extras = _extras(extra_files)
    if not item_ids and not extras:
        raise KrdError("Choose at least one device or name a firmware file")
    if len(extras) > MAX_EXTRA_FILES:
        raise KrdError(f"Too many named files (limit {MAX_EXTRA_FILES})")

    tarball, _ = _paths(cache_root)
    catalog = load_catalog(cache_root) if tarball.exists() else None
    skipped: List[str] = []
    if catalog:
        entries, skipped = _entries_from_cache(tarball, catalog, item_ids, extras)
    else:
        if item_ids:
            raise KrdError("Download the firmware release first; the device list comes from it")

        def remote() -> Iterator[Tuple[str, bytes]]:
            seen: Set[str] = set()
            for name, alternatives, _required in extras:
                for candidate in [name, *alternatives]:
                    data = _fetch_remote_file(candidate)
                    if data is not None:
                        if candidate not in seen:
                            seen.add(candidate)
                            yield candidate, data
                        break
                else:
                    if _required:
                        skipped.append(name)

        entries = remote()

    added, replaced = _write_archive(folder, entries)
    return {
        "archive": CUSTOM_ARCHIVE,
        "size": (folder / CUSTOM_ARCHIVE).stat().st_size,
        "added": added,
        "skipped": skipped,
        "replaced": [r for r in replaced if r != CUSTOM_ARCHIVE],
        "tag": FIRMWARE_TAG,
    }


def install_full_firmware(
    folder: Path, cache_root: Path, progress: Optional[Callable[[int, int], None]] = None
) -> dict:
    """Put the complete release on the disk (downloading it to the cache first if needed)."""
    tarball, _ = _paths(cache_root)
    if not tarball.exists():
        download_source(cache_root, progress)
    replaced = _remove_archives(folder)
    target = folder / FULL_ARCHIVE
    tmp = target.with_name(target.name + ".tmp")
    tmp.unlink(missing_ok=True)
    try:
        try:
            os.link(tarball, tmp)
        except OSError:  # another filesystem
            shutil.copyfile(tarball, tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return {
        "archive": FULL_ARCHIVE,
        "size": target.stat().st_size,
        "replaced": replaced,
        "tag": FIRMWARE_TAG,
    }

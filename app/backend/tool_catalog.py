"""Rescue and maintenance tools that can be downloaded from the Assets tab.

Each tool knows where its releases are published, which file to take, and how to verify it. Versions
come from the project's GitHub releases page; if that cannot be reached (offline, rate limit), a
known-good release is offered instead so a download is still possible.
"""

import logging
import re
import time
from typing import Callable, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

GITHUB_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
CACHE_SECONDS = 600
_release_cache: Dict[str, Tuple[float, dict]] = {}

_HASH_LINE = re.compile(r"^([0-9a-fA-F]{40}|[0-9a-fA-F]{64})\s+\*?(\S+)\s*$")

# Ubuntu releases Rescuezilla is built on, with a readable label.
_UBUNTU_BASES = {
    "noble": "Ubuntu 24.04 LTS",
    "oracular": "Ubuntu 24.10",
    "questing": "Ubuntu 25.10",
    "resolute": "Ubuntu 26.04 LTS",
}


def parse_checksum_file(text: str) -> Dict[str, str]:
    """Read a ``<hash>  <filename>`` list (sha1sum / sha256sum format) into {filename: hash}."""
    hashes: Dict[str, str] = {}
    for line in text.splitlines():
        match = _HASH_LINE.match(line.strip())
        if match:
            hashes[match.group(2)] = match.group(1).lower()
    return hashes


def _latest_release(repo: str) -> Optional[dict]:
    """Latest GitHub release of a repository (cached), or None when it cannot be fetched."""
    cached = _release_cache.get(repo)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]
    try:
        response = requests.get(
            GITHUB_LATEST.format(repo=repo),
            headers={"Accept": "application/vnd.github+json"},
            timeout=15,
        )
        response.raise_for_status()
        release = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not read releases of %s: %s", repo, exc)
        return None
    _release_cache[repo] = (time.time(), release)
    return release


def _download_text(url: str) -> str:
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        logger.warning("Could not read %s: %s", url, exc)
        return ""


def _size_label(size_bytes: int) -> str:
    return f"~{size_bytes / 1e9:.1f} GB" if size_bytes >= 1e9 else f"~{size_bytes / 1e6:.0f} MB"


# ---------------------------------------------------------------------------
# Rescuezilla
# ---------------------------------------------------------------------------

_RESCUEZILLA_ISO = re.compile(r"^rescuezilla-(?P<ver>\d+(?:\.\d+)*)-64bit\.(?P<base>[a-z]+)\.iso$")

_RESCUEZILLA_NOTES = (
    "Graphical backup and restore (Clonezilla-based). NFS mode reads the system on demand; "
    "ISO mode needs about 4 GB of RAM."
)

_RESCUEZILLA_FALLBACK = [
    {
        "version": "2.6.2",
        "name": "Rescuezilla 2.6.2 (Ubuntu 24.04 LTS)",
        "iso_url": "https://github.com/rescuezilla/rescuezilla/releases/download/2.6.2/rescuezilla-2.6.2-64bit.noble.iso",
        "iso_name": "rescuezilla-2.6.2-64bit.noble.iso",
        "dest_folder": "rescuezilla-2.6.2",
        "size_est": "~1.6 GB",
        "checksum": "sha256:285db0af83213e2297490ca1cfd74ecd607c3b0a2f1d14e11a8412c0b71eea50",
        "recommended": True,
        "notes": _RESCUEZILLA_NOTES,
    }
]


def rescuezilla_versions() -> List[dict]:
    release = _latest_release("rescuezilla/rescuezilla")
    if not release:
        return [dict(v) for v in _RESCUEZILLA_FALLBACK]

    assets = {a["name"]: a for a in release.get("assets", [])}
    checksums: Dict[str, str] = {}
    if "SHA256SUM" in assets:
        checksums = parse_checksum_file(_download_text(assets["SHA256SUM"]["browser_download_url"]))

    versions: List[dict] = []
    for name, asset in assets.items():
        match = _RESCUEZILLA_ISO.match(name)
        if not match:
            continue
        ver, base = match.group("ver"), match.group("base")
        is_lts_default = base == "noble"
        version = ver if is_lts_default else f"{ver}-{base}"
        entry = {
            "version": version,
            "name": f"Rescuezilla {ver} ({_UBUNTU_BASES.get(base, base)})",
            "iso_url": asset["browser_download_url"],
            "iso_name": name,
            "dest_folder": f"rescuezilla-{version}",
            "size_est": _size_label(asset.get("size", 0)),
            "recommended": is_lts_default,
            "notes": _RESCUEZILLA_NOTES,
        }
        if name in checksums:
            entry["checksum"] = f"sha256:{checksums[name]}"
        versions.append(entry)

    if not versions:
        return [dict(v) for v in _RESCUEZILLA_FALLBACK]
    versions.sort(key=lambda v: (not v["recommended"], v["name"]))
    return versions


# ---------------------------------------------------------------------------
# ShredOS
# ---------------------------------------------------------------------------

_SHREDOS_ISO = re.compile(
    r"^shredos-[^_]+_\d+_x86-64_v(?P<ver>\d+(?:\.\d+)*)_\d+(?P<variant>_lite|_plus-partition)?\.iso$"
)

_SHREDOS_FULL_NOTES = "Needs at least 2 GB of RAM. Starts the nwipe disk eraser."
_SHREDOS_LITE_NOTES = (
    "Runs in 512 MB of RAM, for low-resource machines. Starts the nwipe disk eraser."
)
_SHREDOS_WARNING = (
    "ShredOS erases disks. Boot it only on machines whose data you no longer need, and "
    "check the disk list before starting a wipe."
)

_SHREDOS_BASE = "https://github.com/PartialVolume/shredos.x86_64/releases/download/"
_SHREDOS_FALLBACK = [
    {
        "version": "0.42",
        "name": "ShredOS 0.42",
        "iso_url": _SHREDOS_BASE
        + "v2025.11_31_x86-64_0.42/shredos-2025.11_31_x86-64_v0.42_20260716.iso",
        "iso_name": "shredos-2025.11_31_x86-64_v0.42_20260716.iso",
        "dest_folder": "shredos-0.42",
        "size_est": "~361 MB",
        "checksum": "sha1:ef4b41f95f96b2bc80ee3fbe2e9ca9ea51750569",
        "recommended": True,
        "notes": _SHREDOS_FULL_NOTES,
        "warning": _SHREDOS_WARNING,
    },
    {
        "version": "0.42-lite",
        "name": "ShredOS 0.42 Lite",
        "iso_url": _SHREDOS_BASE
        + "v2025.11_31_x86-64_0.42/shredos-2025.11_31_x86-64_v0.42_20260716_lite.iso",
        "iso_name": "shredos-2025.11_31_x86-64_v0.42_20260716_lite.iso",
        "dest_folder": "shredos-0.42-lite",
        "size_est": "~108 MB",
        "checksum": "sha1:72a73f8dde047401df783f7b0df940ed02f2de99",
        "recommended": False,
        "notes": _SHREDOS_LITE_NOTES,
        "warning": _SHREDOS_WARNING,
    },
]


def shredos_versions() -> List[dict]:
    release = _latest_release("PartialVolume/shredos.x86_64")
    if not release:
        return [dict(v) for v in _SHREDOS_FALLBACK]

    assets = {a["name"]: a for a in release.get("assets", [])}
    versions: List[dict] = []
    for name, asset in assets.items():
        match = _SHREDOS_ISO.match(name)
        # The "plus-partition" image is meant for USB sticks with a data partition, not for PXE.
        if not match or match.group("variant") == "_plus-partition":
            continue
        is_lite = match.group("variant") == "_lite"
        ver = match.group("ver")
        entry = {
            "version": f"{ver}-lite" if is_lite else ver,
            "name": f"ShredOS {ver}{' Lite' if is_lite else ''}",
            "iso_url": asset["browser_download_url"],
            "iso_name": name,
            "dest_folder": f"shredos-{ver}-lite" if is_lite else f"shredos-{ver}",
            "size_est": _size_label(asset.get("size", 0)),
            "recommended": not is_lite,
            "notes": _SHREDOS_LITE_NOTES if is_lite else _SHREDOS_FULL_NOTES,
            "warning": _SHREDOS_WARNING,
        }
        sha_asset = assets.get(name + ".sha1")
        if sha_asset:
            digest = parse_checksum_file(_download_text(sha_asset["browser_download_url"])).get(
                name
            )
            if digest:
                entry["checksum"] = f"sha1:{digest}"
        versions.append(entry)

    if not versions:
        return [dict(v) for v in _SHREDOS_FALLBACK]
    versions.sort(key=lambda v: (not v["recommended"], v["name"]))
    return versions


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

TOOLS: List[dict] = [
    {
        "id": "rescuezilla",
        "name": "Rescuezilla",
        "icon": "💾",
        "description": "Disk backup, restore and cloning with a simple graphical interface.",
        "homepage": "https://rescuezilla.com",
        "scenario": "rescuezilla",
        "catalog_key": "rescuezilla",
        "warning": "",
        "versions": rescuezilla_versions,
    },
    {
        "id": "shredos",
        "name": "ShredOS",
        "icon": "🧨",
        "description": "Secure disk erasure (nwipe) for retiring or reusing machines.",
        "homepage": "https://github.com/PartialVolume/shredos.x86_64",
        "scenario": "shredos",
        "catalog_key": "shredos",
        "warning": _SHREDOS_WARNING,
        "versions": shredos_versions,
    },
]

_FETCHERS: Dict[str, Callable[[], List[dict]]] = {t["id"]: t["versions"] for t in TOOLS}


def list_tools() -> List[dict]:
    """Every tool with its currently available versions."""
    return [
        {**{k: v for k, v in t.items() if k != "versions"}, "versions": t["versions"]()}
        for t in TOOLS
    ]


def tool_versions(tool_id: str) -> Optional[List[dict]]:
    fetch = _FETCHERS.get(tool_id)
    return fetch() if fetch else None

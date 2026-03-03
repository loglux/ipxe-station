"""Shared state, models, and utility functions for all route modules."""

import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Dict, List

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory monitoring state
# ---------------------------------------------------------------------------

SYSTEM_LOGS: list = []
MAX_LOGS = 1000
PXE_CLIENTS: Dict[str, dict] = {}
PXE_LOOP_WINDOW_SECONDS = 30
PXE_LOOP_THRESHOLD = 3
PXE_STALL_THRESHOLD_SECONDS = 15
PXE_CLIENT_TTL_SECONDS = 3600  # evict clients not seen in 1 hour

# ---------------------------------------------------------------------------
# Download progress tracking (thread-safe)
# ---------------------------------------------------------------------------

download_progress: dict = {}
download_progress_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Filesystem roots
# ---------------------------------------------------------------------------

BASE_ROOT = Path(os.getenv("IPXE_DATA_ROOT", "/srv"))
try:
    BASE_ROOT.mkdir(parents=True, exist_ok=True)
except PermissionError:
    BASE_ROOT = Path("/tmp/ipxe")
    BASE_ROOT.mkdir(parents=True, exist_ok=True)

HTTP_ROOT = BASE_ROOT / "http"
IPXE_ROOT = BASE_ROOT / "ipxe"
TFTP_ROOT = BASE_ROOT / "tftp"

for _d in (HTTP_ROOT, IPXE_ROOT, TFTP_ROOT):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Settings model and persistence
# ---------------------------------------------------------------------------

SETTINGS_FILE = IPXE_ROOT / "settings.json"


def _auto_detect_ip() -> str:
    """Detect the outbound IP address of this machine."""
    import socket

    env_ip = os.getenv("PXE_SERVER_IP", "")
    if env_ip:
        return env_ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.1"


class SettingsModel(BaseModel):
    server_ip: str = Field(default_factory=_auto_detect_ip)
    http_port: int = 9021
    tftp_port: int = 69
    default_timeout: int = 30000  # milliseconds
    default_entry: str = ""
    auto_extraction: bool = True
    poll_interval: int = 2000  # milliseconds
    theme: str = "light"
    show_file_sizes: bool = True
    show_timestamps: bool = True
    # Host-side path that the NAS exports via NFS (not the Docker-internal path).
    # Used when generating NFS boot entries for Ubuntu Server ISOs.
    nfs_root: str = os.getenv("NFS_ROOT", "")
    active_preseed_profile: str = "debian_minimal"


def load_settings() -> SettingsModel:
    """Load settings from file or return defaults."""
    if SETTINGS_FILE.exists():
        import json

        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                return SettingsModel(**data)
        except Exception as e:
            add_log("system", "warning", f"Failed to load settings from {SETTINGS_FILE}: {str(e)}")
    return SettingsModel()


def save_settings(settings: SettingsModel):
    """Save settings to file."""
    import json

    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings.model_dump(), f, indent=2)


# ---------------------------------------------------------------------------
# Monitoring log helpers
# ---------------------------------------------------------------------------


def add_log(log_type: str, level: str, message: str, **context):
    """Add a log entry to the system logs."""
    global SYSTEM_LOGS
    from datetime import datetime

    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": log_type,
        "level": level,
        "message": message,
    }
    log_entry.update({k: v for k, v in context.items() if v is not None})

    SYSTEM_LOGS.append(log_entry)

    if len(SYSTEM_LOGS) > MAX_LOGS:
        SYSTEM_LOGS = SYSTEM_LOGS[-MAX_LOGS:]

    logger.debug("[%s] [%s] %s", log_type, level, message)


# ---------------------------------------------------------------------------
# PXE boot session tracking
# ---------------------------------------------------------------------------


def _get_pxe_client_state(client_ip: str) -> dict:
    state = PXE_CLIENTS.setdefault(
        client_ip,
        {
            "recent_ipxe_efi_requests": deque(),
            "last_boot_script_at": 0.0,
            "loop_warning_at": 0.0,
            "last_stage": None,
            "first_seen_at": 0.0,
            "last_seen_at": 0.0,
            "last_event_at": 0.0,
            "stalled_warning_at": 0.0,
            "boot_script_fetches": 0,
            "kernel_fetches": 0,
            "initrd_fetches": 0,
            "beacon_hits": 0,
            "event_count": 0,
        },
    )
    return state


def _record_boot_event(
    client_ip: str,
    stage: str,
    message: str,
    *,
    level: str = "info",
    protocol: str | None = None,
    filename: str | None = None,
):
    """Record a structured PXE/iPXE boot flow event."""
    now = time.time()
    state = _get_pxe_client_state(client_ip)
    if not state["first_seen_at"]:
        state["first_seen_at"] = now
    state["last_seen_at"] = now
    state["last_event_at"] = now
    state["last_stage"] = stage
    state["event_count"] += 1
    if stage == "boot_script":
        state["boot_script_fetches"] += 1
    elif stage == "kernel":
        state["kernel_fetches"] += 1
    elif stage == "initrd":
        state["initrd_fetches"] += 1
    elif stage == "beacon":
        state["beacon_hits"] += 1
    add_log(
        "boot",
        level,
        message,
        client_ip=client_ip,
        stage=stage,
        protocol=protocol,
        filename=filename,
    )


def _track_ipxe_loop(client_ip: str, filename: str):
    """Detect repeated iPXE binary requests without a boot script fetch."""
    if filename != "ipxe.efi":
        return

    now = time.time()
    state = _get_pxe_client_state(client_ip)
    requests = state["recent_ipxe_efi_requests"]

    requests.append(now)
    while requests and now - requests[0] > PXE_LOOP_WINDOW_SECONDS:
        requests.popleft()

    if state["last_boot_script_at"] >= requests[0]:
        return

    if (
        len(requests) >= PXE_LOOP_THRESHOLD
        and now - state["loop_warning_at"] > PXE_LOOP_WINDOW_SECONDS
    ):
        state["loop_warning_at"] = now
        _record_boot_event(
            client_ip,
            "suspected_loop",
            (
                f"Suspected iPXE chainload loop: {len(requests)} requests for {filename} "
                f"in {PXE_LOOP_WINDOW_SECONDS}s without boot.ipxe fetch"
            ),
            level="warning",
            protocol="tftp",
            filename=filename,
        )


def _session_status(state: dict, now: float | None = None) -> str:
    """Summarise current client boot state into a compact status."""
    now = now or time.time()
    if state["kernel_fetches"] or state["initrd_fetches"]:
        return "boot_assets_requested"
    if state["boot_script_fetches"]:
        return "boot_script_fetched"
    if (
        state["last_stage"] == "ipxe_binary"
        and state["last_seen_at"]
        and now - state["last_seen_at"] > PXE_STALL_THRESHOLD_SECONDS
    ):
        return "stalled_after_ipxe"
    if state["last_stage"] == "suspected_loop":
        return "suspected_loop"
    if state["last_stage"] == "ipxe_binary":
        return "waiting_for_boot_script"
    return state["last_stage"] or "unknown"


def _build_boot_session(client_ip: str, state: dict, now: float | None = None) -> dict:
    """Return a serialisable boot session summary for monitoring UI."""
    now = now or time.time()
    return {
        "client_ip": client_ip,
        "first_seen_at": state["first_seen_at"],
        "last_seen_at": state["last_seen_at"],
        "last_stage": state["last_stage"],
        "status": _session_status(state, now),
        "event_count": state["event_count"],
        "boot_script_fetches": state["boot_script_fetches"],
        "kernel_fetches": state["kernel_fetches"],
        "initrd_fetches": state["initrd_fetches"],
        "beacon_hits": state["beacon_hits"],
        "recent_ipxe_requests": len(state["recent_ipxe_efi_requests"]),
        "seconds_since_seen": (
            round(max(0.0, now - state["last_seen_at"]), 1) if state["last_seen_at"] else None
        ),
    }


def _refresh_boot_sessions(now: float | None = None) -> List[dict]:
    """Update stalled warnings and return current boot sessions."""
    now = now or time.time()

    # Evict clients not seen within TTL
    stale = [
        ip
        for ip, s in PXE_CLIENTS.items()
        if s["last_seen_at"] and now - s["last_seen_at"] > PXE_CLIENT_TTL_SECONDS
    ]
    for ip in stale:
        del PXE_CLIENTS[ip]

    sessions = []
    for client_ip, state in PXE_CLIENTS.items():
        if (
            state["last_stage"] == "ipxe_binary"
            and not state["boot_script_fetches"]
            and state["last_seen_at"]
            and now - state["last_seen_at"] > PXE_STALL_THRESHOLD_SECONDS
            and now - state["stalled_warning_at"] > PXE_STALL_THRESHOLD_SECONDS
        ):
            state["stalled_warning_at"] = now
            _record_boot_event(
                client_ip,
                "stalled_after_ipxe",
                (
                    f"Client stalled after iPXE binary: no boot.ipxe fetch within "
                    f"{PXE_STALL_THRESHOLD_SECONDS}s"
                ),
                level="warning",
                protocol="boot",
                filename="ipxe.efi",
            )
        sessions.append(_build_boot_session(client_ip, state, now))

    sessions.sort(key=lambda session: session["last_seen_at"] or 0.0, reverse=True)
    return sessions


def _record_http_boot_flow(request: Request, path: str, status_code: int):
    """Capture meaningful boot asset HTTP requests as structured events."""
    client_ip = request.client.host if request.client else "unknown"
    normalized = path.lstrip("/")
    stage = None

    if normalized == "ipxe/boot.ipxe":
        state = _get_pxe_client_state(client_ip)
        state["last_boot_script_at"] = time.time()
        state["recent_ipxe_efi_requests"].clear()
        stage = "boot_script"
    elif normalized.endswith(("/vmlinuz", "/linux", "/k-x86_64", "/k-x86")):
        stage = "kernel"
    elif "initrd" in normalized or "sysresccd.img" in normalized:
        stage = "initrd"

    if not stage:
        return

    level = "info" if status_code < 400 else "warning"
    _record_boot_event(
        client_ip,
        stage,
        f"HTTP boot asset request: {normalized} -> {status_code}",
        level=level,
        protocol="http",
        filename=normalized.rsplit("/", 1)[-1],
    )


# ---------------------------------------------------------------------------
# Filesystem utilities
# ---------------------------------------------------------------------------


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
        squashfs = None

        if prefix == "kaspersky":
            # Prefer live/ layout (standard KRD ISO extraction)
            live_vmlinuz = path / "live" / "vmlinuz"
            live_initrd = path / "live" / "initrd.img"
            live_squashfs = path / "live" / "filesystem.squashfs"
            if live_vmlinuz.exists():
                kernel = f"{path.name}/live/vmlinuz"
            if live_initrd.exists():
                initrd = f"{path.name}/live/initrd.img"
            if live_squashfs.exists():
                squashfs = f"{path.name}/live/filesystem.squashfs"
            # Fallback: root-level files
            if not kernel:
                for name in ["vmlinuz", "k-x86_64", "k-x86"]:
                    candidate = path / name
                    if candidate.exists():
                        kernel = f"{path.name}/{name}"
                        break
            if not initrd:
                for name in ["initrd.img", "initrd.xz", "initrd"]:
                    candidate = path / name
                    if candidate.exists():
                        initrd = f"{path.name}/{name}"
                        break
            # Fallback: krd/boot/grub/ layout
            if not kernel:
                candidate = path / "krd" / "boot" / "grub" / "k-x86_64"
                if candidate.exists():
                    kernel = f"{path.name}/krd/boot/grub/k-x86_64"
            if not initrd:
                for name in ["initrd.xz", "initrd.img"]:
                    candidate = path / "krd" / "boot" / "grub" / name
                    if candidate.exists():
                        initrd = f"{path.name}/krd/boot/grub/{name}"
                        break
        elif prefix in ("rescue", "systemrescue"):
            for name in ["vmlinuz", "linux"]:
                candidate = path / name
                if candidate.exists():
                    kernel = f"{path.name}/{name}"
                    break
            for name in ["initrd", "initrd.img", "initrd.lz", "initrd.xz"]:
                candidate = path / name
                if candidate.exists():
                    initrd = f"{path.name}/{name}"
                    break
            # Fallback: sysresccd/boot/x86_64/ layout (extracted ISO)
            if not kernel:
                candidate = path / "sysresccd" / "boot" / "x86_64" / "vmlinuz"
                if candidate.exists():
                    kernel = f"{path.name}/sysresccd/boot/x86_64/vmlinuz"
            if not initrd:
                candidate = path / "sysresccd" / "boot" / "x86_64" / "sysresccd.img"
                if candidate.exists():
                    initrd = f"{path.name}/sysresccd/boot/x86_64/sysresccd.img"
        elif prefix == "debian":
            for name in ["linux", "vmlinuz"]:
                candidate = path / name
                if candidate.exists():
                    kernel = f"{path.name}/{name}"
                    break
            for name in ["initrd.gz", "initrd", "initrd.img"]:
                candidate = path / name
                if candidate.exists():
                    initrd = f"{path.name}/{name}"
                    break

            if not kernel:
                for name in ["vmlinuz", "linux"]:
                    candidate = path / "live" / name
                    if candidate.exists():
                        kernel = f"{path.name}/live/{name}"
                        break
            if not initrd:
                for name in ["initrd.img", "initrd", "initrd.gz"]:
                    candidate = path / "live" / name
                    if candidate.exists():
                        initrd = f"{path.name}/live/{name}"
                        break
            live_squashfs = path / "live" / "filesystem.squashfs"
            if live_squashfs.exists():
                squashfs = f"{path.name}/live/filesystem.squashfs"
        else:
            for name in ["vmlinuz", "linux"]:
                candidate = path / name
                if candidate.exists():
                    kernel = f"{path.name}/{name}"
                    break
            for name in ["initrd", "initrd.img", "initrd.lz", "initrd.xz"]:
                candidate = path / name
                if candidate.exists():
                    initrd = f"{path.name}/{name}"
                    break
            # Fallback: casper/ layout (Ubuntu extracted ISO)
            if not kernel:
                for name in ["vmlinuz"]:
                    candidate = path / "casper" / name
                    if candidate.exists():
                        kernel = f"{path.name}/casper/{name}"
                        break
            if not initrd:
                for name in ["initrd", "initrd.lz"]:
                    candidate = path / "casper" / name
                    if candidate.exists():
                        initrd = f"{path.name}/casper/{name}"
                        break
            # Detect squashfs for Ubuntu casper boot.
            # Note: fetch= is broken on Ubuntu 22.04+ via iPXE (causes black screen /
            # "no medium found"). squashfs field is retained for catalog info only;
            # NFS is the correct boot method for Server, HTTP ISO for Desktop.
            casper = path / "casper"
            for sqname in ["ubuntu-server-minimal.squashfs", "filesystem.squashfs"]:
                candidate = casper / sqname
                if candidate.exists():
                    squashfs = f"{path.name}/casper/{sqname}"
                    break

        for item in path.glob("*.iso"):
            iso = f"{path.name}/{item.name}"
            break
        for item in path.glob("*.wim"):
            wim = f"{path.name}/{item.name}"
            break

        results.append(
            {
                "version": version,
                "kernel": kernel,
                "initrd": initrd,
                "iso": iso,
                "wim": wim,
                "squashfs": squashfs,
            }
        )
    return results


def _resolve_within_root(
    root: Path,
    raw_path: str,
    *,
    allow_empty: bool = False,
    fallback_name: str = "",
    path_label: str = "path",
) -> Path:
    """Resolve a user-supplied path and ensure it stays inside root."""
    value = (raw_path or "").strip()

    if not value:
        if fallback_name:
            value = fallback_name
        elif allow_empty:
            return root.resolve()
        else:
            raise HTTPException(status_code=400, detail=f"Missing {path_label}")

    candidate = Path(value)
    if candidate.is_absolute():
        raise HTTPException(
            status_code=400, detail=f"Invalid {path_label}: absolute paths are not allowed"
        )

    resolved = (root / candidate).resolve()
    root_resolved = root.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid {path_label}: path escapes root directory"
        )

    return resolved


def _validate_filename(filename: str) -> str:
    """Validate uploaded filename and reject traversal attempts."""
    value = (filename or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="Invalid filename: empty filename")

    name = Path(value).name
    if value != name or name in {".", ".."}:
        raise HTTPException(
            status_code=400, detail="Invalid filename: nested paths are not allowed"
        )

    return name

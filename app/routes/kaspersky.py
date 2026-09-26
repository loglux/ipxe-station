"""Kaspersky Rescue Disk maintenance: fresh antivirus databases and the firmware the disk lacks."""

import json
import time
from typing import List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.backend import krd_maintenance as krd

from . import state
from .state import add_log

kaspersky_router = APIRouter(prefix="/api/kaspersky", tags=["kaspersky"])

MAX_REPORT_BYTES = 512 * 1024
KEEP_REPORTS = 20


def _folder(name: str):
    try:
        return krd.resolve_folder(state.HTTP_ROOT, name)
    except krd.KrdError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _backup_root():
    return state.BASE_ROOT / "_src" / "krd-backups"


def _reports_file():
    return state.IPXE_ROOT / "krd-firmware-reports.json"


def _load_reports() -> list:
    try:
        data = json.loads(_reports_file().read_text())
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _job_key(folder_name: str, kind: str) -> str:
    return f"{folder_name}:{kind}"


@kaspersky_router.get("")
def list_folders():
    """Extracted Kaspersky disks, with the state of their databases and firmware."""
    folders = []
    for folder in krd.find_krd_folders(state.HTTP_ROOT):
        folders.append(
            {
                "name": folder.name,
                "version": krd.krd_version(folder),
                "bases": krd.local_bases_timestamp(folder),
                "bases_label": krd.format_timestamp(krd.local_bases_timestamp(folder)),
                "firmware": krd.firmware_state(folder),
            }
        )
    return {"folders": folders}


@kaspersky_router.get("/{name}/bases")
def check_bases(name: str):
    """Compare the databases on the disk with what Kaspersky publishes now."""
    return krd.bases_status(_folder(name))


class UpdateRequest(BaseModel):
    force: bool = False


@kaspersky_router.post("/{name}/bases/update")
def update_bases(name: str, payload: UpdateRequest = UpdateRequest()):
    folder = _folder(name)

    def work(progress):
        result = krd.update_bases(folder, _backup_root(), progress, force=payload.force)
        add_log("system", "info", f"Kaspersky databases ({name}): {result['message']}")
        return result

    if not krd.start_job(_job_key(name, "bases"), work):
        raise HTTPException(status_code=409, detail="An update is already running")
    return {"started": True}


@kaspersky_router.get("/{name}/jobs/{kind}")
def job(name: str, kind: str):
    if kind not in ("bases", "firmware"):
        raise HTTPException(status_code=404, detail="Unknown job")
    _folder(name)
    return krd.job_status(_job_key(name, kind))


# --- firmware -------------------------------------------------------------


@kaspersky_router.get("/{name}/firmware")
def firmware_overview(name: str):
    folder = _folder(name)
    return {
        **krd.firmware_state(folder),
        "presets": krd.FIRMWARE_PRESETS,
        "reports": _load_reports(),
    }


class ScanRequest(BaseModel):
    text: str = Field("", max_length=MAX_REPORT_BYTES)


@kaspersky_router.post("/{name}/firmware/scan")
def scan_dmesg(name: str, payload: ScanRequest):
    """Which firmware files the kernel could not load, from pasted ``dmesg`` output."""
    _folder(name)
    missing = krd.parse_missing_firmware(payload.text)
    return {"missing": missing, "presets": krd.presets_covering(m["name"] for m in missing)}


@kaspersky_router.post("/{name}/firmware/report")
async def report_dmesg(name: str, request: Request):
    """Receive ``dmesg`` straight from a laptop running KRD (``wget --post-file``)."""
    _folder(name)
    body = await request.body()
    if len(body) > MAX_REPORT_BYTES:
        raise HTTPException(status_code=413, detail="Report too large")
    missing = krd.parse_missing_firmware(body.decode("utf-8", errors="replace"))
    client = request.client.host if request.client else ""
    reports = _load_reports()
    reports.append(
        {
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "client": client,
            "missing": missing,
        }
    )
    _reports_file().write_text(json.dumps(reports[-KEEP_REPORTS:], indent=2))
    add_log("system", "info", f"Firmware report from {client}: {len(missing)} missing file(s)")
    return {"received": True, "missing": missing}


class FirmwareFile(BaseModel):
    name: str = Field(..., max_length=120)
    alternatives: List[str] = Field(default_factory=list, max_length=80)


class FirmwareBuild(BaseModel):
    presets: List[str] = Field(default_factory=list)
    files: List[FirmwareFile] = Field(default_factory=list)


@kaspersky_router.post("/{name}/firmware/custom")
def build_custom(name: str, payload: FirmwareBuild):
    """Build the small archive with the chosen devices and named files."""
    folder = _folder(name)

    def work(progress):
        result = krd.build_custom_firmware(
            folder, payload.presets, [f.model_dump() for f in payload.files]
        )
        added = len(result["added"])
        add_log("system", "info", f"Firmware archive built for {name}: {added} file(s)")
        return result

    if not krd.start_job(_job_key(name, "firmware"), work):
        raise HTTPException(status_code=409, detail="A firmware job is already running")
    return {"started": True}


@kaspersky_router.post("/{name}/firmware/full")
def install_full(name: str):
    """Download the complete linux-firmware release for the KRD kernel."""
    folder = _folder(name)

    def work(progress):
        result = krd.install_full_firmware(folder, progress)
        add_log("system", "info", f"Full firmware archive installed for {name}")
        return result

    if not krd.start_job(_job_key(name, "firmware"), work):
        raise HTTPException(status_code=409, detail="A firmware job is already running")
    return {"started": True}


@kaspersky_router.delete("/{name}/firmware")
def remove_firmware(name: str):
    return {"removed": krd.remove_firmware(_folder(name))}

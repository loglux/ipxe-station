"""Kaspersky Rescue Disk maintenance: fresh antivirus databases and the firmware the disk lacks."""

import json
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.backend import krd_display as display
from app.backend import krd_firmware as fw
from app.backend import krd_maintenance as krd
from app.backend.device_scenarios import MATCH_FIELDS

from . import ipxe as ipxe_routes
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
                "firmware": fw.firmware_state(folder),
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


def _cache_root():
    return state.BASE_ROOT / "_src" / "linux-firmware"


@kaspersky_router.get("/firmware-source")
def firmware_source():
    """The downloaded firmware release (if any) and the devices it covers."""
    info = fw.source_state(_cache_root())
    return {
        **info,
        "catalog": fw.catalog_summary(_cache_root()),
        "categories": fw.CATEGORY_LABELS,
        "large_bytes": fw.LARGE_SELECTION_BYTES,
    }


@kaspersky_router.post("/firmware-source/download")
def download_firmware_source():
    def work(progress):
        result = fw.download_source(_cache_root(), progress)
        add_log("system", "info", f"Firmware release {fw.FIRMWARE_TAG} downloaded and verified")
        return result

    if not krd.start_job("source:download", work):
        raise HTTPException(status_code=409, detail="The download is already running")
    return {"started": True}


@kaspersky_router.get("/firmware-source/job")
def firmware_source_job():
    return krd.job_status("source:download")


@kaspersky_router.delete("/firmware-source")
def remove_firmware_source():
    return {"removed": fw.remove_source(_cache_root())}


def _reports() -> list:
    try:
        data = json.loads(_reports_file().read_text())
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def record_firmware_report(client: str, device: dict, text: str) -> list:
    """Remember which firmware a machine could not find. One entry per machine, newest wins."""
    missing = fw.parse_missing_firmware(text)
    who = device.get("mac") or client
    entry = {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "client": client,
        "mac": device.get("mac", ""),
        "device": " ".join(p for p in (device.get("manufacturer"), device.get("product")) if p),
        "missing": missing,
    }
    reports = [r for r in _reports() if (r.get("mac") or r.get("client")) != who]
    reports.append(entry)
    _reports_file().write_text(json.dumps(reports[-KEEP_REPORTS:], indent=2))
    add_log(
        "system",
        "info",
        f"Firmware report from {entry['device'] or client}: {len(missing)} missing file(s)",
    )
    return missing


def _names_of(missing: list) -> list:
    names = []
    for item in missing:
        names.extend([item["name"], *item.get("alternatives", []), *item.get("companions", [])])
    return names


@kaspersky_router.get("/firmware-reports")
def firmware_reports():
    """What machines reported as missing, and the catalog entries that would fix it."""
    reports = _reports()
    recommended: list = []
    for report in reports:
        report["items"] = fw.items_covering(_cache_root(), _names_of(report.get("missing", [])))
        recommended.extend(i for i in report["items"] if i not in recommended)
    return {"reports": list(reversed(reports)), "recommended": recommended}


@kaspersky_router.delete("/firmware-reports")
def clear_firmware_reports():
    _reports_file().unlink(missing_ok=True)
    return {"cleared": True}


@kaspersky_router.get("/{name}/firmware")
def firmware_overview(name: str):
    return fw.firmware_state(_folder(name))


class ScanRequest(BaseModel):
    text: str = Field("", max_length=MAX_REPORT_BYTES)


@kaspersky_router.post("/{name}/firmware/scan")
def scan_dmesg(name: str, payload: ScanRequest):
    """Which firmware files the kernel could not load, from pasted ``dmesg`` output."""
    _folder(name)
    missing = fw.parse_missing_firmware(payload.text)
    return {"missing": missing, "items": fw.items_covering(_cache_root(), _names_of(missing))}


@kaspersky_router.post("/{name}/firmware/report")
async def report_dmesg(name: str, request: Request):
    """Receive ``dmesg`` sent by hand (``wget --post-file``); the boot script sends it by itself."""
    _folder(name)
    body = await request.body()
    if len(body) > MAX_REPORT_BYTES:
        raise HTTPException(status_code=413, detail="Report too large")
    client = request.client.host if request.client else ""
    missing = record_firmware_report(client, {}, body.decode("utf-8", errors="replace"))
    return {"received": True, "missing": missing}


class FirmwareFile(BaseModel):
    name: str = Field(..., max_length=120)
    alternatives: List[str] = Field(default_factory=list, max_length=80)


class FirmwareBuild(BaseModel):
    items: List[str] = Field(default_factory=list, max_length=800)
    files: List[FirmwareFile] = Field(default_factory=list)


@kaspersky_router.post("/{name}/firmware/custom")
def build_custom(name: str, payload: FirmwareBuild):
    """Build the small archive from the chosen devices and named files."""
    folder = _folder(name)

    def work(progress):
        result = fw.build_custom_firmware(
            folder, _cache_root(), payload.items, [f.model_dump() for f in payload.files]
        )
        added = len(result["added"])
        add_log("system", "info", f"Firmware archive built for {name}: {added} file(s)")
        return result

    if not krd.start_job(_job_key(name, "firmware"), work):
        raise HTTPException(status_code=409, detail="A firmware job is already running")
    return {"started": True}


@kaspersky_router.post("/{name}/firmware/full")
def install_full(name: str):
    """Put the complete release on the disk (it is downloaded first if it is not cached yet)."""
    folder = _folder(name)

    def work(progress):
        result = fw.install_full_firmware(folder, _cache_root(), progress)
        add_log("system", "info", f"Full firmware archive installed for {name}")
        return result

    if not krd.start_job(_job_key(name, "firmware"), work):
        raise HTTPException(status_code=409, detail="A firmware job is already running")
    return {"started": True}


@kaspersky_router.delete("/{name}/firmware")
def remove_firmware(name: str):
    return {"removed": fw.remove_firmware(_folder(name))}


# --- screen: text size and video mode -----------------------------------------


def display_settings() -> display.DisplaySettings:
    return display.load_display_settings(state.IPXE_ROOT / "krd-display.json")


def _is_krd_entry(entry) -> bool:
    return "kaspersky" in (entry.kernel or "").lower() and "boot=live" in (entry.cmdline or "")


def _is_hook_token(token: str) -> bool:
    return token.startswith("live-config.hooks=") and display.HOOK_PATH in token


def _menu_display_state(model) -> dict:
    entries = [e for e in (model.entries if model else []) if _is_krd_entry(e)]
    return {
        "entries": [{"name": e.name, "title": e.title} for e in entries],
        "hook": bool(entries) and all(any(map(_is_hook_token, e.cmdline.split())) for e in entries),
        "native_video": bool(entries)
        and all("nomodeset" not in e.cmdline.split() for e in entries),
    }


def _patched_cmdline(cmdline: str, hook: Optional[bool], native_video: Optional[bool]) -> str:
    tokens = cmdline.split()
    if hook is not None:
        tokens = [t for t in tokens if not _is_hook_token(t)]
        if hook:
            tokens.append(display.hook_argument())
    if native_video is not None:
        tokens = [t for t in tokens if t != "nomodeset"]
        if not native_video:
            tokens.append("nomodeset")
    return " ".join(tokens)


@kaspersky_router.get("/display")
def get_display():
    """Text size settings, and how the Kaspersky entries of the menu are set up for them."""
    settings = display_settings()
    return {
        "default": settings.default,
        "report_firmware": settings.report_firmware,
        "rules": [r.model_dump() for r in settings.rules],
        "match_fields": [
            f for f in MATCH_FIELDS if f in ("manufacturer", "product", "sku", "family")
        ],
        "menu": _menu_display_state(ipxe_routes.saved_menu()),
    }


@kaspersky_router.put("/display")
def put_display(payload: display.DisplaySettings):
    display.save_display_settings(state.IPXE_ROOT / "krd-display.json", payload)
    return {"success": True}


@kaspersky_router.get("/display/preview")
def preview_display(request: Request):
    """The text size a machine would get, from the fields it reports (brand, model, ...)."""
    fields = {n: request.query_params.get(n, "")[:200] for n in display.HOOK_QUERY_FIELDS}
    scale, source = display.resolve_scale(display_settings(), state._normalise_inventory(fields))
    return {"scale": scale, "source": source}


class DisplayMenuChange(BaseModel):
    hook: Optional[bool] = None
    native_video: Optional[bool] = None


@kaspersky_router.post("/display/menu")
def change_display_menu(payload: DisplayMenuChange):
    """Switch the text-size script and the native video mode in the Kaspersky menu entries."""
    model = ipxe_routes.saved_menu()
    entries = [e for e in (model.entries if model else []) if _is_krd_entry(e)]
    if not entries:
        raise HTTPException(status_code=404, detail="No Kaspersky Rescue Disk 24 entry in the menu")
    for entry in entries:
        entry.cmdline = _patched_cmdline(entry.cmdline, payload.hook, payload.native_video)
    result = ipxe_routes.save_menu(model)
    if not result.get("valid"):
        raise HTTPException(status_code=422, detail=result.get("message") or "Menu not valid")
    add_log(
        "system",
        "info",
        f"Kaspersky menu entries updated for screen settings: {payload.model_dump()}",
    )
    return {"menu": _menu_display_state(model), "warnings": result.get("warnings", [])}

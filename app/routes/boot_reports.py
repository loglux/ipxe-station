"""Boot reports from live systems: list, read, and choose which menu entries ask for them."""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.backend import boot_report

from . import ipxe as ipxe_routes
from . import state
from .state import add_log

boot_reports_router = APIRouter(prefix="/api/boot-reports", tags=["boot-reports"])


def reports_file():
    return state.IPXE_ROOT / "boot-reports.json"


def _eligible(entry) -> bool:
    """Live-config systems (Debian Live and the like). Kaspersky has its own script."""
    return (
        "boot=live" in (entry.cmdline or "").split()
        and "kaspersky" not in (entry.kernel or "").lower()
    )


def _entries(model) -> list:
    return [e for e in (model.entries if model else []) if _eligible(e)]


def _entry_state(entry) -> dict:
    tokens = (entry.cmdline or "").split()
    return {
        "name": entry.name,
        "title": entry.title,
        "enabled": any(map(boot_report.is_hook_token, tokens)),
        **boot_report.entry_mode(tokens, entry.kernel, state.HTTP_ROOT),
    }


def debug_file():
    return state.IPXE_ROOT / "boot-debug.json"


@boot_reports_router.get("/debug")
def debug_reports():
    """What people ran the diagnostic script on a machine and sent back (newest first)."""
    return {"reports": boot_report.debug_reports(debug_file())}


@boot_reports_router.get("")
def list_reports(mac: str = ""):
    return {"reports": boot_report.summaries(reports_file(), mac)}


@boot_reports_router.get("/entries")
def report_entries():
    """The menu entries that can send a boot report, and which of them do."""
    return {"entries": [_entry_state(e) for e in _entries(ipxe_routes.saved_menu())]}


class EntriesChoice(BaseModel):
    enabled: List[str] = Field(default_factory=list, max_length=200)


@boot_reports_router.post("/entries")
def choose_entries(payload: EntriesChoice):
    """Make exactly the chosen entries ask for a boot report."""
    model = ipxe_routes.saved_menu()
    entries = _entries(model)
    if not entries:
        raise HTTPException(status_code=404, detail="No live Linux entry in the menu")
    by_name = {e.name: e for e in entries}
    for name in payload.enabled:
        if name not in by_name:
            raise HTTPException(status_code=422, detail=f"'{name}' cannot send a boot report")
        mode = _entry_state(by_name[name])
        if not mode["supported"]:
            raise HTTPException(status_code=422, detail=f"{mode['title']}: {mode['reason']}")

    settings = state.load_settings()
    base = f"http://{settings.server_ip}:{settings.http_port}{boot_report.REPORT_PATH}"
    wanted_folders = set()
    all_folders = set()
    for entry in entries:
        folder = boot_report.image_folder(entry.kernel)
        tokens = [t for t in entry.cmdline.split() if not boot_report.is_hook_token(t)]
        all_folders.add(folder)
        if entry.name in payload.enabled:
            if boot_report.entry_mode(tokens, entry.kernel, state.HTTP_ROOT)["mode"] == "medium":
                tokens.append(boot_report.MEDIUM_HOOK_ARG)
                wanted_folders.add(folder)
            else:
                tokens.append(boot_report.hook_argument())
        entry.cmdline = " ".join(tokens)
    result = ipxe_routes.save_menu(model)
    if not result.get("valid"):
        raise HTTPException(status_code=422, detail=result.get("message") or "Menu not valid")

    # the script file on the medium follows the menu: there where an NFS entry asks, gone elsewhere
    for folder in wanted_folders:
        boot_report.install_medium_hook(state.HTTP_ROOT, folder, base)
    for folder in all_folders - wanted_folders:
        if folder:
            boot_report.remove_medium_hook(state.HTTP_ROOT, folder)
    add_log("system", "info", f"Boot reports asked for by: {', '.join(payload.enabled) or 'none'}")
    return {"entries": [_entry_state(e) for e in entries], "warnings": result.get("warnings", [])}


@boot_reports_router.get("/{report_id}")
def get_report(report_id: str):
    report = boot_report.get(reports_file(), report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No such report")
    return report


@boot_reports_router.delete("/{report_id}")
def delete_report(report_id: str):
    if not boot_report.delete(reports_file(), report_id):
        raise HTTPException(status_code=404, detail="No such report")
    return {"deleted": True}

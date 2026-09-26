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
    return {
        "name": entry.name,
        "title": entry.title,
        "enabled": any(map(boot_report.is_hook_token, entry.cmdline.split())),
    }


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
    names = {e.name for e in entries}
    unknown = [n for n in payload.enabled if n not in names]
    if unknown:
        raise HTTPException(status_code=422, detail=f"'{unknown[0]}' cannot send a boot report")
    for entry in entries:
        tokens = [t for t in entry.cmdline.split() if not boot_report.is_hook_token(t)]
        if entry.name in payload.enabled:
            tokens.append(boot_report.hook_argument())
        entry.cmdline = " ".join(tokens)
    result = ipxe_routes.save_menu(model)
    if not result.get("valid"):
        raise HTTPException(status_code=422, detail=result.get("message") or "Menu not valid")
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

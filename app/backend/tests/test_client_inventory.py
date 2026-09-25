"""Client inventory: what a booting machine reports about itself (brand, model, serial, NIC)."""

import pytest
from fastapi.testclient import TestClient

import app.routes.state as state
from app.backend.config import settings
from app.backend.ipxe_manager import iPXEGenerator, iPXEMenu
from app.main import app

client = TestClient(app)

DELL = {
    "mac": "00:BE:43:6B:6A:AE",
    "uuid": "4C4C4544-0047-1048-8035-C8C04F4B3533",
    "manufacturer": "Dell Inc.",
    "product": "Latitude 5530",
    "sku": "0B3D",
    "serial": "ABC1234",
    "bios_version": "1.20.0",
    "bios_date": "07/10/2024",
    "platform": "efi",
    "arch": "x86_64",
    "busid": "01-80-86-1a-1c",
}


@pytest.fixture(autouse=True)
def isolated_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "INVENTORY_FILE", tmp_path / "clients.json")
    monkeypatch.setattr(state, "_inventory_loaded", False)
    state.CLIENT_INVENTORY.clear()
    state.SYSTEM_LOGS.clear()
    yield
    state.CLIENT_INVENTORY.clear()


def _client_info_logs():
    return [log["message"] for log in state.SYSTEM_LOGS if log.get("stage") == "inventory"]


def test_report_is_stored_and_described_in_the_log():
    record = state.record_client_inventory("192.168.10.35", DELL)

    assert record["manufacturer"] == "Dell Inc."
    assert record["product"] == "Latitude 5530"
    assert record["mac"] == "00:be:43:6b:6a:ae"
    assert record["uuid"] == "4c4c4544-0047-1048-8035-c8c04f4b3533"
    assert record["nic_pci"] == "8086:1a1c"
    assert record["boots"] == 1
    (line,) = _client_info_logs()
    assert "Dell Inc. Latitude 5530" in line
    assert "SKU 0B3D" in line and "serial ABC1234" in line and "BIOS 1.20.0" in line
    assert "NIC 8086:1a1c" in line and "efi x86_64" in line


def test_same_machine_updates_one_record_and_keeps_known_values():
    state.record_client_inventory("192.168.10.35", DELL)
    later = dict(DELL, product="", sku="")  # a later report with empty fields

    record = state.record_client_inventory("192.168.10.36", later)

    assert len(state.list_client_inventory()) == 1
    assert record["boots"] == 2
    assert record["product"] == "Latitude 5530"  # not erased by the empty value
    assert record["client_ip"] == "192.168.10.36"


def test_values_are_cleaned_and_bounded():
    record = state.record_client_inventory(
        "10.0.0.5",
        {
            "mac": "not-a-mac",
            "uuid": "00000000-0000-0000-0000-000000000000",
            "manufacturer": "Evil\nCorp\x00\x1b[31m",
            "product": "P" * 500,
            "serial": "S1",
        },
    )

    assert not record.get("mac") and not record.get("uuid")  # invalid values are dropped
    assert "\n" not in record["manufacturer"] and "\x00" not in record["manufacturer"]
    assert len(record["product"]) == 80
    assert record["id"] == "10.0.0.5"  # no valid uuid or mac, so keyed by IP


def test_report_without_identifying_data_is_ignored():
    assert state.record_client_inventory("10.0.0.5", {"platform": "efi"}) is None
    assert state.list_client_inventory() == []


def test_list_is_capped(monkeypatch):
    monkeypatch.setattr(state, "INVENTORY_MAX_CLIENTS", 2)
    for i in range(3):
        state.record_client_inventory("10.0.0.1", {"mac": f"00:00:00:00:00:0{i}"})

    assert len(state.list_client_inventory()) == 2


def test_inventory_survives_a_restart(tmp_path, monkeypatch):
    state.record_client_inventory("192.168.10.35", DELL)
    assert (tmp_path / "clients.json").exists()

    state.CLIENT_INVENTORY.clear()
    monkeypatch.setattr(state, "_inventory_loaded", False)

    (record,) = state.list_client_inventory()
    assert record["product"] == "Latitude 5530"


def test_endpoint_records_client_and_hides_its_own_request_line():
    resp = client.get("/client-info", params=DELL)

    assert resp.status_code == 200
    (record,) = client.get("/api/monitoring/clients").json()["clients"]
    assert record["manufacturer"] == "Dell Inc." and record["nic_pci"] == "8086:1a1c"
    assert not any("/client-info" in log["message"] for log in state.SYSTEM_LOGS)
    assert len(_client_info_logs()) == 1


def test_report_stays_open_in_token_mode_but_the_client_list_does_not(monkeypatch):
    monkeypatch.setattr(settings, "security_mode", "token")
    monkeypatch.setattr(settings, "api_token", "secret-token")

    assert client.get("/client-info", params=DELL).status_code == 200
    assert client.get("/api/monitoring/clients").status_code == 401
    ok = client.get("/api/monitoring/clients", headers={"Authorization": "Bearer secret-token"})
    assert ok.status_code == 200 and len(ok.json()["clients"]) == 1


def test_menu_script_reports_to_this_server_and_never_blocks_the_menu():
    script = iPXEGenerator.generate_ipxe_script(iPXEMenu(server_ip="10.0.0.1", http_port=8080))

    assert "imgfetch --name client-info http://10.0.0.1:8080/client-info?" in script
    assert "|| echo Client info report skipped" in script
    assert "imgfree client-info ||" in script
    assert script.index("client-info") < script.index(":start")


def test_menu_script_without_server_address_skips_the_report():
    script = iPXEGenerator.generate_ipxe_script(iPXEMenu())

    assert "client-info" not in script

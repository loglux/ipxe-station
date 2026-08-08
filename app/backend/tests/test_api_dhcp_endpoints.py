"""HTTP-level tests for /api/dhcp routes."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_server_types_lists_four_types():
    resp = client.get("/api/dhcp/server-types")
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()["server_types"]]
    assert set(ids) == {"dnsmasq", "isc-dhcp", "mikrotik", "windows"}


def test_generate_config_uses_request_body_not_defaults():
    """Regression test: the endpoint used to declare its inputs as bare function
    params, which FastAPI reads as query params — but the frontend always sent a
    JSON body, so every custom value was silently ignored and the endpoint always
    returned the hardcoded-default dnsmasq config regardless of user input."""
    resp = client.post(
        "/api/dhcp/config/generate",
        json={
            "server_type": "isc-dhcp",
            "pxe_server_ip": "10.99.99.99",
            "http_port": 1234,
            "tftp_port": 5678,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "isc-dhcp"
    assert "10.99.99.99" in data["config"]


def test_generate_config_defaults_when_body_omitted():
    resp = client.post("/api/dhcp/config/generate", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "dnsmasq"
    assert "192.168.10.32" in data["config"]


def test_generate_config_http_boot_flag_reaches_generator():
    resp = client.post(
        "/api/dhcp/config/generate",
        json={"pxe_server_ip": "10.0.0.5", "http_port": 9021, "http_boot": True},
    )
    assert resp.status_code == 200
    config_text = resp.json()["config"]
    assert "dhcp-vendorclass=set:httpclient,HTTPClient" in config_text
    assert "10.0.0.5:9021/ipxe.efi" in config_text


def test_generate_config_unknown_server_type_returns_400():
    resp = client.post("/api/dhcp/config/generate", json={"server_type": "nope"})
    assert resp.status_code == 400

"""The monitoring log should show boot traffic and problems, not the UI's own polling."""

from fastapi.testclient import TestClient

from app.main import app
from app.routes.state import SYSTEM_LOGS

client = TestClient(app)


def _http_messages() -> list[str]:
    return [log["message"] for log in SYSTEM_LOGS if log["type"] == "http"]


def test_successful_api_reads_are_not_logged():
    """Regression test: every UI poll (proxy status, download progress, settings, ...) was
    written to the system log, burying real boot activity."""
    SYSTEM_LOGS.clear()

    assert client.get("/api/proxy-dhcp/status").status_code == 200
    assert client.get("/api/assets/download/progress").status_code == 200
    assert client.get("/api/settings").status_code == 200

    assert _http_messages() == []


def test_failed_api_reads_are_still_logged():
    SYSTEM_LOGS.clear()

    assert client.get("/api/no-such-endpoint").status_code == 404

    assert any("GET /api/no-such-endpoint - 404" in m for m in _http_messages())


def test_api_writes_are_still_logged():
    SYSTEM_LOGS.clear()

    resp = client.post("/api/ipxe/validate", json={"title": "Menu", "entries": []})
    assert resp.status_code == 200

    assert any("POST /api/ipxe/validate - 200" in m for m in _http_messages())


def test_boot_file_requests_are_still_logged():
    SYSTEM_LOGS.clear()

    client.get("/ipxe/boot.ipxe")

    assert any("GET /ipxe/boot.ipxe" in m for m in _http_messages())

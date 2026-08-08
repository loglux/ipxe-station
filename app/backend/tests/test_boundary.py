from fastapi.testclient import TestClient

from app.main import app
from app.routes import boundary

client = TestClient(app)


def test_security_mode_off_allows_unauthenticated_requests():
    assert boundary.settings.security_mode == "off"
    resp = client.get("/api/settings")
    assert resp.status_code != 401


def test_security_mode_token_rejects_missing_token(monkeypatch):
    monkeypatch.setattr(boundary.settings, "security_mode", "token")
    monkeypatch.setattr(boundary.settings, "api_token", "secret-token")

    resp = client.get("/api/settings")

    assert resp.status_code == 401


def test_security_mode_token_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(boundary.settings, "security_mode", "token")
    monkeypatch.setattr(boundary.settings, "api_token", "secret-token")

    resp = client.get("/api/settings", headers={"Authorization": "Bearer wrong-token"})

    assert resp.status_code == 401


def test_security_mode_token_accepts_correct_token(monkeypatch):
    monkeypatch.setattr(boundary.settings, "security_mode", "token")
    monkeypatch.setattr(boundary.settings, "api_token", "secret-token")

    resp = client.get("/api/settings", headers={"Authorization": "Bearer secret-token"})

    assert resp.status_code != 401


def test_security_mode_token_without_configured_token_fails_closed(monkeypatch):
    monkeypatch.setattr(boundary.settings, "security_mode", "token")
    monkeypatch.setattr(boundary.settings, "api_token", "")

    resp = client.get("/api/settings", headers={"Authorization": "Bearer anything"})

    assert resp.status_code == 500

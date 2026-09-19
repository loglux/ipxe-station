"""HTTP-level tests for /api/monitoring/services."""

import subprocess
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _fake_run(returncodes):
    """Build a subprocess.run stand-in that answers by the command being run."""

    def fake(cmd, *args, **kwargs):
        return SimpleNamespace(returncode=returncodes[cmd[0]], stdout="", stderr="")

    return fake


def test_rsyslog_reported_running_when_process_exists(monkeypatch):
    """Regression test: rsyslog used to be checked with `service rsyslog status`, which
    always fails in the container (no init script) and showed a false 'stopped'."""
    # `service` fails (as in the container) while the rsyslogd process is alive
    monkeypatch.setattr(subprocess, "run", _fake_run({"service": 1, "pgrep": 0}))

    resp = client.get("/api/monitoring/services")

    assert resp.status_code == 200
    assert resp.json()["services"]["rsyslog"]["status"] == "running"


def test_rsyslog_reported_stopped_when_no_process(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run({"service": 0, "pgrep": 1}))

    resp = client.get("/api/monitoring/services")

    assert resp.json()["services"]["rsyslog"]["status"] == "stopped"

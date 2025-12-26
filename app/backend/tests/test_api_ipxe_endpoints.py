import json

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def sample_menu():
    return {
        "title": "Menu",
        "timeout": 1000,
        "default_entry": "ubuntu",
        "server_ip": "10.0.0.1",
        "http_port": 8080,
        "entries": [
            {
                "name": "ubuntu",
                "title": "Ubuntu",
                "kernel": "ubuntu/vmlinuz",
                "initrd": "ubuntu/initrd",
                "cmdline": "ip=dhcp",
                "entry_type": "boot",
                "boot_mode": "netboot",
            }
        ],
    }


def test_validate_endpoint():
    resp = client.post("/api/ipxe/validate", json=sample_menu())
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == []
    assert isinstance(data["warnings"], list)


def test_generate_endpoint():
    resp = client.post("/api/ipxe/generate", json=sample_menu())
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert "kernel http://10.0.0.1:8080/ubuntu/vmlinuz" in data["script"]
    assert isinstance(data["warnings"], list)

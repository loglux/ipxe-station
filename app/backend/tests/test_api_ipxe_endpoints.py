from fastapi.testclient import TestClient

from app.main import TFTP_ROOT, app

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


def test_save_autoexec_endpoint():
    payload = {"content": "#!ipxe\necho test\n"}
    resp = client.post("/api/boot/autoexec", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    saved = TFTP_ROOT / "autoexec.ipxe"
    assert saved.exists()
    assert saved.read_text() == payload["content"]


def test_upload_rejects_path_traversal_dest():
    files = {"file": ("poc.txt", b"owned", "text/plain")}
    resp = client.post("/api/assets/upload?dest=../../escape", files=files)
    assert resp.status_code == 400
    assert "Invalid dest" in resp.json()["detail"]


def test_upload_rejects_nested_filename():
    files = {"file": ("../escape.txt", b"owned", "text/plain")}
    resp = client.post("/api/assets/upload?dest=safe", files=files)
    assert resp.status_code == 400
    assert "Invalid filename" in resp.json()["detail"]


def test_download_rejects_absolute_dest():
    resp = client.post(
        "/api/assets/download",
        json={"url": "https://example.com/image.iso", "dest": "/tmp/escape.iso"},
    )
    assert resp.status_code == 400
    assert "Invalid dest" in resp.json()["detail"]


def test_extract_iso_rejects_path_traversal_iso_path():
    resp = client.post(
        "/api/assets/extract-iso",
        json={"iso_path": "../escape.iso"},
    )
    assert resp.status_code == 400
    assert "Invalid iso_path" in resp.json()["detail"]

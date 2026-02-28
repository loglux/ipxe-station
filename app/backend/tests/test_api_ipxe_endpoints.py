from fastapi.testclient import TestClient

from app.main import (
    IPXE_ROOT,
    PXE_CLIENTS,
    SYSTEM_LOGS,
    TFTP_ROOT,
    _refresh_boot_sessions,
    _track_ipxe_loop,
    app,
)

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


def setup_function():
    SYSTEM_LOGS.clear()
    PXE_CLIENTS.clear()


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


def test_delete_autoexec_endpoint():
    saved = TFTP_ROOT / "autoexec.ipxe"
    saved.write_text("#!ipxe\necho test\n")

    resp = client.delete("/api/boot/autoexec")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert not saved.exists()


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


def test_boot_script_http_request_creates_structured_boot_log():
    boot_script = IPXE_ROOT / "boot.ipxe"
    boot_script.write_text("#!ipxe\n")

    resp = client.get("/ipxe/boot.ipxe")
    assert resp.status_code == 200

    logs_resp = client.get("/api/monitoring/logs?type=boot")
    assert logs_resp.status_code == 200
    logs = logs_resp.json()["logs"]

    assert any(
        log["stage"] == "boot_script"
        and log["protocol"] == "http"
        and log["filename"] == "boot.ipxe"
        for log in logs
    )


def test_repeated_ipxe_requests_trigger_loop_warning():
    for _ in range(3):
        _track_ipxe_loop("192.168.10.225", "ipxe.efi")

    warning_logs = [
        log for log in SYSTEM_LOGS if log["type"] == "boot" and log["stage"] == "suspected_loop"
    ]

    assert warning_logs
    assert warning_logs[-1]["level"] == "warning"
    assert warning_logs[-1]["client_ip"] == "192.168.10.225"


def test_boot_ping_creates_beacon_event():
    resp = client.get("/api/boot/ping?stage=pre-menu")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["stage"] == "pre-menu"

    logs_resp = client.get("/api/monitoring/logs?type=boot")
    logs = logs_resp.json()["logs"]
    assert any(log["stage"] == "beacon" and log["protocol"] == "http" for log in logs)


def test_boot_sessions_mark_client_as_stalled_after_ipxe_binary():
    PXE_CLIENTS.setdefault(
        "192.168.10.225",
        {
            "recent_ipxe_efi_requests": [],
            "last_boot_script_at": 0.0,
            "loop_warning_at": 0.0,
            "last_stage": "ipxe_binary",
            "first_seen_at": 100.0,
            "last_seen_at": 100.0,
            "last_event_at": 100.0,
            "stalled_warning_at": 0.0,
            "boot_script_fetches": 0,
            "kernel_fetches": 0,
            "initrd_fetches": 0,
            "beacon_hits": 0,
            "event_count": 1,
        },
    )

    sessions = _refresh_boot_sessions(now=116.0)
    assert sessions[0]["client_ip"] == "192.168.10.225"
    assert sessions[0]["status"] == "stalled_after_ipxe"

    warning_logs = [
        log for log in SYSTEM_LOGS if log["type"] == "boot" and log["stage"] == "stalled_after_ipxe"
    ]
    assert warning_logs


def test_boot_sessions_endpoint_returns_summary():
    client.get("/api/boot/ping?stage=test")

    resp = client.get("/api/monitoring/boot-sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["sessions"]
    assert data["sessions"][0]["status"] in {
        "beacon",
        "waiting_for_boot_script",
        "boot_script_fetched",
    }

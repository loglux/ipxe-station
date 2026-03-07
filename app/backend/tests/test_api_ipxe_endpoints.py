from fastapi.testclient import TestClient

from app.main import (
    HTTP_ROOT,
    IPXE_ROOT,
    PXE_CLIENTS,
    SYSTEM_LOGS,
    TFTP_ROOT,
    _refresh_boot_sessions,
    _track_ipxe_loop,
    app,
)
from app.routes.assets import PRESETS_DIR
from app.routes.state import SETTINGS_FILE

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
    (TFTP_ROOT / "autoexec.ipxe").unlink(missing_ok=True)
    (HTTP_ROOT / "preseed.cfg").unlink(missing_ok=True)
    preseed_dir = HTTP_ROOT / "preseed"
    if preseed_dir.exists():
        for path in preseed_dir.glob("*.cfg"):
            path.unlink()
    SETTINGS_FILE.unlink(missing_ok=True)
    if PRESETS_DIR.exists():
        for path in PRESETS_DIR.glob("*.json"):
            path.unlink()


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
    # server_ip/http_port from payload are always overridden by live settings
    assert "/http/ubuntu/vmlinuz" in data["script"]
    assert "10.0.0.1" not in data["script"]
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


def test_save_preseed_endpoint():
    payload = {"profile": "lab", "content": "# Debian preseed\n"}
    resp = client.post("/api/boot/preseed", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["profile"] == "lab"
    assert data["active_profile"] == "lab"
    saved = HTTP_ROOT / "preseed.cfg"
    assert saved.exists()
    assert saved.read_text() == payload["content"]
    named = HTTP_ROOT / "preseed" / "lab.cfg"
    assert named.exists()
    assert named.read_text() == payload["content"]


def test_delete_preseed_endpoint():
    client.post("/api/boot/preseed", json={"profile": "lab", "content": "# Debian preseed\n"})

    resp = client.delete("/api/boot/preseed?profile=lab")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert not (HTTP_ROOT / "preseed" / "lab.cfg").exists()


def test_preseed_profiles_endpoint_lists_active_profile():
    client.post(
        "/api/boot/preseed",
        json={"profile": "lab", "content": "# lab\n", "activate": False},
    )
    client.post("/api/boot/preseed", json={"profile": "desktop", "content": "# desktop\n"})

    resp = client.get("/api/boot/preseed/profiles")
    assert resp.status_code == 200
    data = resp.json()
    assert "lab" in data["profiles"]
    assert "desktop" in data["profiles"]
    assert data["active_profile"] == "desktop"


def test_activate_preseed_profile_updates_root_alias():
    client.post(
        "/api/boot/preseed",
        json={"profile": "lab", "content": "# lab\n", "activate": False},
    )
    client.post("/api/boot/preseed", json={"profile": "desktop", "content": "# desktop\n"})

    resp = client.post("/api/boot/preseed/activate", json={"profile": "lab"})
    assert resp.status_code == 200
    assert resp.json()["active_profile"] == "lab"
    assert (HTTP_ROOT / "preseed.cfg").read_text() == "# lab\n"


def test_preseed_served_from_root_endpoint():
    client.post("/api/boot/preseed", json={"profile": "lab", "content": "# Debian preseed\n"})

    resp = client.get("/preseed.cfg")
    assert resp.status_code == 200
    assert "# Debian preseed" in resp.text


def test_named_preseed_profile_served_from_profile_endpoint():
    client.post(
        "/api/boot/preseed",
        json={"profile": "desktop", "content": "# Desktop profile\n", "activate": False},
    )

    resp = client.get("/preseed/desktop.cfg")
    assert resp.status_code == 200
    assert "# Desktop profile" in resp.text


def test_assets_boot_recipe_accepts_preseed_profile():
    version_dir = HTTP_ROOT / "debian-13.3.0"
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / "linux").write_text("kernel")
    (version_dir / "initrd.gz").write_text("initrd")

    resp = client.get(
        "/api/assets/boot-recipe?version_path=debian-13.3.0&scenario=debian_preseed&preseed_profile=desktop"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert "/preseed/desktop.cfg" in data["options"][0]["cmdline"]


def test_debian_versions_endpoint_returns_full_download_products():
    resp = client.get("/api/assets/versions/debian")
    assert resp.status_code == 200
    data = resp.json()
    products = data["products"]

    assert any(product["kind"] == "installer_bootstrap" for product in products)
    assert any(product["kind"] == "installer_iso" for product in products)
    assert any(product["kind"] == "live_iso" for product in products)
    assert any(product["experimental"] is True for product in products if "experimental" in product)


def test_presets_endpoint_returns_seeded_system_presets():
    resp = client.get("/api/assets/presets")
    assert resp.status_code == 200
    data = resp.json()
    names = [preset["name"] for preset in data["presets"]]
    sections = [preset["section"] for preset in data["presets"]]
    assert "Ubuntu" in names
    assert "Debian" in names
    assert "Tools" in names
    assert "Antivirus" in names
    assert "ubuntu" in sections
    assert "debian" in sections
    assert "tools" in sections
    assert "antivirus" in sections


def test_create_user_preset_and_list_it():
    payload = {
        "name": "Hiren ISO",
        "category": "utility",
        "mode": "acquire",
        "section": "tools",
        "method": "memdisk_iso_or_img",
        "description": "Manual ISO preset",
        "params": {"memdisk_mode": "iso"},
    }
    create_resp = client.post("/api/assets/presets", json=payload)
    assert create_resp.status_code == 200
    created = create_resp.json()["preset"]
    assert created["source"] == "user"
    assert created["name"] == "Hiren ISO"

    list_resp = client.get("/api/assets/presets")
    assert list_resp.status_code == 200
    data = list_resp.json()["presets"]
    assert any(p["name"] == "Hiren ISO" and p["source"] == "user" for p in data)


def test_update_user_preset():
    create_resp = client.post(
        "/api/assets/presets",
        json={"name": "Temp preset", "section": "tools", "mode": "acquire"},
    )
    assert create_resp.status_code == 200
    preset_id = create_resp.json()["preset"]["id"]

    patch_resp = client.patch(
        f"/api/assets/presets/{preset_id}",
        json={"name": "Updated preset", "enabled": False, "order": 999},
    )
    assert patch_resp.status_code == 200
    preset = patch_resp.json()["preset"]
    assert preset["name"] == "Updated preset"
    assert preset["enabled"] is False
    assert preset["order"] == 999


def test_delete_user_preset():
    create_resp = client.post(
        "/api/assets/presets",
        json={"name": "Delete me", "section": "tools", "mode": "acquire"},
    )
    assert create_resp.status_code == 200
    preset_id = create_resp.json()["preset"]["id"]

    del_resp = client.delete(f"/api/assets/presets/{preset_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    list_resp = client.get("/api/assets/presets")
    assert list_resp.status_code == 200
    assert all(p["id"] != preset_id for p in list_resp.json()["presets"])


def test_system_preset_is_read_only():
    patch_resp = client.patch("/api/assets/presets/acquire_ubuntu", json={"enabled": False})
    assert patch_resp.status_code == 403
    assert "read-only" in patch_resp.json()["detail"]

    del_resp = client.delete("/api/assets/presets/acquire_ubuntu")
    assert del_resp.status_code == 403
    assert "read-only" in del_resp.json()["detail"]


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


def test_monitoring_logs_download_returns_attachment_text():
    SYSTEM_LOGS.extend(
        [
            {
                "timestamp": "2026-03-07 01:00:00",
                "type": "tftp",
                "level": "info",
                "message": "TFTP request from 192.168.10.10",
            },
            {
                "timestamp": "2026-03-07 01:00:01",
                "type": "http",
                "level": "warning",
                "message": "Slow response",
            },
        ]
    )

    resp = client.get("/api/monitoring/logs/download?type=tftp")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "attachment; filename=" in resp.headers["content-disposition"]
    assert "[info] [tftp] TFTP request from 192.168.10.10" in resp.text
    assert "[warning] [http] Slow response" not in resp.text


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

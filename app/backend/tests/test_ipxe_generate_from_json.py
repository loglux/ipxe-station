import json

from app.backend.ipxe_manager import iPXEManager


def test_generate_from_json_success():
    manager = iPXEManager()
    payload = {
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

    ok, msg, script, warnings = manager.generate_from_json(json.dumps(payload))
    assert ok
    assert "ubuntu/vmlinuz" in script
    assert any("kernel file missing" in w for w in warnings)
    assert any("initrd file missing" in w for w in warnings)


def test_generate_from_json_invalid():
    manager = iPXEManager()
    payload = {
        "title": "Menu",
        "timeout": 1000,
        "default_entry": "missing",
        "entries": [],
    }

    ok, msg, script, warnings = manager.generate_from_json(json.dumps(payload))
    assert not ok
    assert script == ""
    assert warnings == []

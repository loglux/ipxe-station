import json

from app.backend.ipxe_manager import iPXEManager


def test_import_menu_from_json_success():
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

    ok, msg, menu = manager.import_menu_from_json(json.dumps(payload))
    assert ok
    assert menu is not None
    assert menu.entries[0].name == "ubuntu"


def test_import_menu_from_json_validation_error():
    manager = iPXEManager()
    payload = {
        "title": "Menu",
        "timeout": 1000,
        # default_entry references missing entry -> schema validator should fail
        "default_entry": "missing",
        "entries": [],
    }

    ok, msg, menu = manager.import_menu_from_json(json.dumps(payload))
    assert not ok
    assert menu is None
    assert "validation failed" in msg.lower()

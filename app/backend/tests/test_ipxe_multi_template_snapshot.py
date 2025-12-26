from app.backend.ipxe_manager import iPXETemplateManager


def test_multi_template_snapshot(tmp_path, monkeypatch):
    # Create dummy files for 24.04 and 22.04 to simulate detection
    for version in ["24.04", "22.04"]:
        base = tmp_path / f"ubuntu-{version}"
        base.mkdir(parents=True, exist_ok=True)
        (base / "vmlinuz").write_text("kernel")
        (base / "initrd").write_text("initrd")
        # Only 24.04 gets ISO and preseed
        if version == "24.04":
            (base / f"ubuntu-{version}-live-server-amd64.iso").write_text("iso")
            (base / "preseed.cfg").write_text("preseed")

    # Patch detector and Path so template sees our temp files
    from app.backend import ipxe_manager as mgr
    from pathlib import Path as RealPath

    def fake_scan(base_path="/srv/http"):
        return {
            "24.04": {"kernel": True, "initrd": True, "iso": True, "preseed": True},
            "22.04": {"kernel": True, "initrd": True, "iso": False, "preseed": False},
        }

    def fake_path(p):
        p_str = str(p)
        if p_str.startswith("/srv/http"):
            p_str = str(tmp_path) + p_str[len("/srv/http"):]
        return RealPath(p_str)

    monkeypatch.setattr(mgr.UbuntuVersionDetector, "scan_available_versions", lambda base_path="/srv/http": fake_scan(str(tmp_path)))
    monkeypatch.setattr(mgr, "Path", fake_path)

    manager = iPXETemplateManager()
    menu = manager.get_ubuntu_multi_template(server_ip="10.0.0.1", port=8080, available_versions=["24.04", "22.04"])
    # Ensure ordering and entries are as expected
    names = [e.name for e in menu.entries if e.entry_type == "boot"]
    assert "memtest" in names  # tool entry
    assert "ubuntu_24_04_netboot" in names
    assert "ubuntu_24_04_live" in names
    assert "ubuntu_24_04_preseed" in names
    assert "ubuntu_24_04_rescue" in names
    assert "ubuntu_22_04_netboot" in names
    assert "ubuntu_22_04_rescue" in names
    assert menu.default_entry == "ubuntu_24_04_netboot"

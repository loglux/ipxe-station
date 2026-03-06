from app.backend.ipxe_manager import iPXEEntry, iPXEMenu, iPXEValidator


def test_validate_menu_missing_initrd():
    menu = iPXEMenu(
        title="Menu",
        timeout=1000,
        default_entry="ubuntu",
        entries=[
            iPXEEntry(
                name="ubuntu",
                title="Ubuntu",
                kernel="ubuntu/vmlinuz",
                initrd=None,
                entry_type="boot",
            )
        ],
    )

    is_valid, errors = iPXEValidator.validate_menu(menu)
    assert not is_valid
    assert any("initrd" in err for err in errors)


def test_validate_menu_invalid_default():
    menu = iPXEMenu(
        title="Menu",
        timeout=1000,
        default_entry="nonexistent",
        entries=[
            iPXEEntry(
                name="ubuntu",
                title="Ubuntu",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                entry_type="boot",
            )
        ],
    )

    is_valid, errors = iPXEValidator.validate_menu(menu)
    assert not is_valid
    assert any("Default entry" in err for err in errors)


def test_lint_live_without_iso_flag():
    menu = iPXEMenu(
        title="Menu",
        timeout=1000,
        default_entry=None,
        entries=[
            iPXEEntry(
                name="ubuntu_live",
                title="Ubuntu Live",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                entry_type="boot",
                boot_mode="live",
                requires_iso=False,
            )
        ],
    )

    warnings = iPXEValidator.lint_menu(menu)
    assert any("requires_iso" in w for w in warnings)


def test_lint_timeout_and_duplicates():
    menu = iPXEMenu(
        title="Menu",
        timeout=0,
        entries=[
            iPXEEntry(
                name="dup",
                title="Ubuntu",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                entry_type="boot",
            ),
            iPXEEntry(
                name="dup",
                title="Ubuntu 2",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                entry_type="boot",
            ),
        ],
    )

    warnings = iPXEValidator.lint_menu(menu)
    assert any("Timeout" in w for w in warnings)
    assert any("Duplicate entry" in w for w in warnings)


def test_lint_missing_files(tmp_path):
    base = tmp_path
    # Only create kernel, omit initrd and ISO
    (base / "ubuntu-24.04").mkdir(parents=True, exist_ok=True)
    (base / "ubuntu-24.04" / "vmlinuz").write_text("kernel")

    menu = iPXEMenu(
        title="Menu",
        timeout=1000,
        entries=[
            iPXEEntry(
                name="ubuntu_live",
                title="Ubuntu Live",
                kernel="ubuntu-24.04/vmlinuz",
                initrd="ubuntu-24.04/initrd",
                entry_type="boot",
                boot_mode="live",
                requires_iso=True,
                cmdline="ip=dhcp boot=casper netboot=url "
                "url=http://localhost:8123/ubuntu-24.04/ubuntu-24.04-live-server-amd64.iso",
            )
        ],
    )

    warnings = iPXEValidator.lint_menu(menu, base_path=str(base))
    assert any("initrd file missing" in w for w in warnings)
    assert any("ISO missing" in w for w in warnings)


def test_lint_local_iso_patch_version_is_valid(tmp_path):
    base = tmp_path
    (base / "live").mkdir(parents=True, exist_ok=True)
    (base / "live" / "vmlinuz").write_text("kernel")
    (base / "live" / "initrd").write_text("initrd")
    (base / "live" / "linux-live-2026.03.1.iso").write_text("iso")

    menu = iPXEMenu(
        title="Menu",
        timeout=1000,
        entries=[
            iPXEEntry(
                name="live_patch",
                title="Live Patch",
                kernel="live/vmlinuz",
                initrd="live/initrd",
                entry_type="boot",
                boot_mode="live",
                requires_iso=True,
                cmdline="ip=dhcp boot=casper netboot=url "
                "url=http://localhost:8123/live/linux-live-2026.03.1.iso",
            )
        ],
    )

    warnings = iPXEValidator.lint_menu(menu, base_path=str(base))
    assert not any("ISO missing" in w for w in warnings)


def test_lint_external_iso_url_is_not_checked_locally(tmp_path):
    base = tmp_path
    (base / "live").mkdir(parents=True, exist_ok=True)
    (base / "live" / "vmlinuz").write_text("kernel")
    (base / "live" / "initrd").write_text("initrd")

    menu = iPXEMenu(
        title="Menu",
        timeout=1000,
        entries=[
            iPXEEntry(
                name="live_external",
                title="Live External",
                kernel="live/vmlinuz",
                initrd="live/initrd",
                entry_type="boot",
                boot_mode="live",
                requires_iso=True,
                cmdline="ip=dhcp boot=casper netboot=url "
                "url=https://cdn.example.org/images/linux-live-2026.03.1.iso",
            )
        ],
    )

    warnings = iPXEValidator.lint_menu(menu, base_path=str(base))
    assert not any("ISO missing" in w for w in warnings)


def test_lint_http_mount_prefix_url_maps_to_base_path(tmp_path):
    base = tmp_path
    (base / "kaspersky-24").mkdir(parents=True, exist_ok=True)
    (base / "kaspersky-24" / "vmlinuz").write_text("kernel")
    (base / "kaspersky-24" / "initrd").write_text("initrd")
    (base / "kaspersky-24" / "krd-24.iso").write_text("iso")

    menu = iPXEMenu(
        title="Menu",
        timeout=1000,
        entries=[
            iPXEEntry(
                name="kaspersky_1",
                title="Kaspersky",
                kernel="kaspersky-24/vmlinuz",
                initrd="kaspersky-24/initrd",
                entry_type="boot",
                boot_mode="live",
                requires_iso=True,
                cmdline="ip=dhcp netboot=url "
                "url=http://localhost:8123/http/kaspersky-24/krd-24.iso",
            )
        ],
    )

    warnings = iPXEValidator.lint_menu(menu, base_path=str(base))
    assert not any("ISO missing" in w for w in warnings)


def test_lint_http_mount_prefix_relative_path_maps_to_base_path(tmp_path):
    base = tmp_path
    (base / "debian-13.3-live-xfce").mkdir(parents=True, exist_ok=True)
    (base / "debian-13.3-live-xfce" / "vmlinuz").write_text("kernel")
    (base / "debian-13.3-live-xfce" / "initrd").write_text("initrd")
    (base / "debian-13.3-live-xfce" / "debian-live-13.3.0-amd64-xfce.iso").write_text("iso")

    menu = iPXEMenu(
        title="Menu",
        timeout=1000,
        entries=[
            iPXEEntry(
                name="debian_live_1",
                title="Debian Live",
                kernel="debian-13.3-live-xfce/vmlinuz",
                initrd="debian-13.3-live-xfce/initrd",
                entry_type="boot",
                boot_mode="live",
                requires_iso=True,
                cmdline="ip=dhcp netboot=url "
                "url=http://localhost:8123/http/debian-13.3-live-xfce/debian-live-13.3.0-amd64-xfce.iso",
            )
        ],
    )

    warnings = iPXEValidator.lint_menu(menu, base_path=str(base))
    assert not any("ISO missing" in w for w in warnings)

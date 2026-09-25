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


def test_lint_live_nfs_does_not_warn():
    """NFS live boot does not need a local ISO — no requires_iso warning."""
    menu = iPXEMenu(
        title="Menu",
        timeout=1000,
        default_entry=None,
        entries=[
            iPXEEntry(
                name="ubuntu_live_nfs",
                title="Ubuntu Live NFS",
                kernel="ubuntu-24.04/vmlinuz",
                initrd="ubuntu-24.04/initrd",
                cmdline="ip=dhcp boot=casper netboot=nfs nfsroot=192.168.1.1:/srv/nfs/ubuntu-24.04",
                entry_type="boot",
                boot_mode="live",
                requires_iso=False,
            )
        ],
    )

    warnings = iPXEValidator.lint_menu(menu)
    assert not any("requires_iso" in w for w in warnings)


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


def _wimboot_menu(initrd: str) -> iPXEMenu:
    return iPXEMenu(
        title="Menu",
        timeout=1000,
        entries=[
            iPXEEntry(
                name="winpe",
                title="WinPE",
                kernel="wimboot",
                initrd=initrd,
                entry_type="boot",
                boot_mode="custom",
            )
        ],
    )


def test_lint_wimboot_multi_file_initrd_checks_each_file(tmp_path):
    base = tmp_path
    (base / "winpe").mkdir(parents=True, exist_ok=True)
    (base / "wimboot").write_text("wimboot")
    for name in ("BCD", "boot.sdi", "boot.wim"):
        (base / "winpe" / name).write_text(name)

    menu = _wimboot_menu("winpe/BCD winpe/boot.sdi winpe/boot.wim")

    warnings = iPXEValidator.lint_menu(menu, base_path=str(base))
    assert not any("initrd file missing" in w for w in warnings)


def test_lint_wimboot_multi_file_initrd_reports_only_missing_file(tmp_path):
    base = tmp_path
    (base / "winpe").mkdir(parents=True, exist_ok=True)
    (base / "wimboot").write_text("wimboot")
    (base / "winpe" / "BCD").write_text("BCD")
    (base / "winpe" / "boot.wim").write_text("wim")

    menu = _wimboot_menu("winpe/BCD winpe/boot.sdi winpe/boot.wim")

    warnings = iPXEValidator.lint_menu(menu, base_path=str(base))
    missing = [w for w in warnings if "initrd file missing" in w]
    assert len(missing) == 1
    assert "boot.sdi" in missing[0]


def _live_menu(cmdline: str) -> iPXEMenu:
    return iPXEMenu(
        title="Menu",
        timeout=1000,
        entries=[
            iPXEEntry(
                name="live",
                title="Live",
                kernel="live/vmlinuz",
                initrd="live/initrd.img",
                cmdline=cmdline,
                boot_mode="live",
                entry_type="boot",
            )
        ],
    )


def _bootif_warnings(cmdline: str) -> list[str]:
    return [w for w in iPXEValidator.lint_menu(_live_menu(cmdline)) if "wrong network card" in w]


def test_lint_warns_when_a_network_live_boot_does_not_pin_the_nic():
    """Regression: live-boot chose the modem (wwan0) over the wired card and never got an IP."""
    assert _bootif_warnings("boot=live components netboot=nfs nfsroot=10.0.0.1:/x")
    assert _bootif_warnings("boot=live components fetch=http://10.0.0.1/live.iso ip=dhcp")


def test_lint_is_quiet_when_the_nic_is_named():
    base = "boot=live components netboot=nfs nfsroot=10.0.0.1:/x"

    assert not _bootif_warnings(base + " BOOTIF=01-${net0/mac:hexhyp}")
    assert not _bootif_warnings(base + " ethdevice=eth0")
    assert not _bootif_warnings(base + " live-netdev=eth0")


def test_lint_ignores_entries_that_are_not_network_live_boots():
    assert not _bootif_warnings("boot=live components")  # live from local media
    assert not _bootif_warnings("ip=dhcp boot=casper netboot=nfs nfsroot=10.0.0.1:/x")

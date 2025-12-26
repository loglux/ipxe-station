import pytest

from app.backend.ipxe_manager import iPXEMenu, iPXEEntry, iPXEValidator


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
            )
        ],
    )

    warnings = iPXEValidator.lint_menu(menu, base_path=str(base))
    assert any("initrd file missing" in w for w in warnings)
    assert any("ISO missing" in w for w in warnings)

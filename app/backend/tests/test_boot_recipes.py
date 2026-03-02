"""Unit tests for app/backend/boot_recipes.py"""

from app.backend.boot_recipes import (
    debian_recipe,
    get_recipe,
    kaspersky_recipe,
    systemrescue_recipe,
    ubuntu_live_recipe,
)

SERVER_IP = "192.168.10.32"
PORT = 9021
BASE = f"http://{SERVER_IP}:{PORT}/http"


# ---------------------------------------------------------------------------
# ubuntu_live_recipe
# ---------------------------------------------------------------------------


class TestUbuntuLiveRecipe:
    def _entry(self, squashfs=None, iso=None):
        return {
            "version": "22.04",
            "kernel": "ubuntu-22.04/casper/vmlinuz",
            "initrd": "ubuntu-22.04/casper/initrd",
            "squashfs": squashfs,
            "iso": iso,
        }

    def test_squashfs_present_produces_recommended_option(self):
        entry = self._entry(squashfs="ubuntu-22.04/casper/ubuntu-server-minimal.squashfs")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT)
        assert len(opts) == 1
        opt = opts[0]
        assert opt.mode == "squashfs"
        assert opt.recommended is True
        assert f"fetch={BASE}/ubuntu-22.04/casper/ubuntu-server-minimal.squashfs" in opt.cmdline
        assert "ip=dhcp" in opt.cmdline

    def test_iso_present_produces_iso_option(self):
        entry = self._entry(iso="ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT)
        assert len(opts) == 1
        opt = opts[0]
        assert opt.mode == "iso"
        assert opt.recommended is False
        assert f"url={BASE}/ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso" in opt.cmdline

    def test_both_squashfs_and_iso_produces_two_options(self):
        entry = self._entry(
            squashfs="ubuntu-22.04/casper/filesystem.squashfs",
            iso="ubuntu-22.04/ubuntu-22.04.iso",
        )
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT)
        assert len(opts) == 2
        modes = {o.mode for o in opts}
        assert modes == {"squashfs", "iso"}
        sq = next(o for o in opts if o.mode == "squashfs")
        assert sq.recommended is True

    def test_no_files_returns_empty(self):
        entry = self._entry()
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT)
        assert opts == []

    def test_kernel_and_initrd_propagated(self):
        entry = self._entry(squashfs="ubuntu-22.04/casper/filesystem.squashfs")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT)
        assert opts[0].kernel == "ubuntu-22.04/casper/vmlinuz"
        assert opts[0].initrd == "ubuntu-22.04/casper/initrd"


# ---------------------------------------------------------------------------
# systemrescue_recipe
# ---------------------------------------------------------------------------


class TestSystemRescueRecipe:
    def _entry(self):
        return {
            "version": "11.01",
            "kernel": "rescue-11.01/sysresccd/boot/x86_64/vmlinuz",
            "initrd": "rescue-11.01/sysresccd/boot/x86_64/sysresccd.img",
            "squashfs": None,
            "iso": None,
        }

    def test_single_http_option(self):
        opts = systemrescue_recipe(self._entry(), SERVER_IP, PORT)
        assert len(opts) == 1
        opt = opts[0]
        assert opt.mode == "http"
        assert opt.recommended is True

    def test_cmdline_contains_base_url(self):
        opts = systemrescue_recipe(self._entry(), SERVER_IP, PORT)
        assert f"archiso_http_srv={BASE}/rescue-11.01/" in opts[0].cmdline
        assert "archisobasedir=sysresccd" in opts[0].cmdline


# ---------------------------------------------------------------------------
# kaspersky_recipe
# ---------------------------------------------------------------------------


class TestKasperskyRecipe:
    def _entry_krd24(self, squashfs=None, iso=None):
        return {
            "version": "24",
            "kernel": "kaspersky-24/live/vmlinuz",
            "initrd": "kaspersky-24/live/initrd.img",
            "squashfs": squashfs,
            "iso": iso,
        }

    def _entry_krd18(self):
        return {
            "version": "18",
            "kernel": "kaspersky-18/krd/boot/grub/k-x86_64",
            "initrd": "kaspersky-18/krd/boot/grub/initrd.xz",
            "squashfs": None,
            "iso": None,
        }

    # --- KRD 18 ---

    def test_krd18_produces_netboot_option(self):
        opts = kaspersky_recipe(self._entry_krd18(), SERVER_IP, PORT)
        assert len(opts) == 1
        opt = opts[0]
        assert opt.mode == "netboot"
        assert opt.recommended is True

    def test_krd18_cmdline_contains_netboot_url(self):
        opts = kaspersky_recipe(self._entry_krd18(), SERVER_IP, PORT)
        cmdline = opts[0].cmdline
        assert f"netboot={BASE}/kaspersky-18/krd/" in cmdline
        assert "dostartx" in cmdline
        assert "net.ifnames=0" in cmdline
        assert "initrd=initrd.xz" in cmdline

    def test_krd18_kernel_and_initrd_preserved(self):
        opts = kaspersky_recipe(self._entry_krd18(), SERVER_IP, PORT)
        assert opts[0].kernel == "kaspersky-18/krd/boot/grub/k-x86_64"
        assert opts[0].initrd == "kaspersky-18/krd/boot/grub/initrd.xz"

    # --- KRD 24 ---

    def test_iso_present_produces_recommended_iso_option(self):
        entry = self._entry_krd24(iso="kaspersky-24/krd-24.iso")
        opts = kaspersky_recipe(entry, SERVER_IP, PORT)
        assert len(opts) == 1
        opt = opts[0]
        assert opt.mode == "iso"
        assert opt.recommended is True
        assert f"fetch={BASE}/kaspersky-24/krd-24.iso" in opt.cmdline
        assert "boot=live" in opt.cmdline

    def test_squashfs_present_produces_squashfs_option(self):
        entry = self._entry_krd24(squashfs="kaspersky-24/live/filesystem.squashfs")
        opts = kaspersky_recipe(entry, SERVER_IP, PORT)
        assert len(opts) == 1
        opt = opts[0]
        assert opt.mode == "squashfs"
        assert f"fetch={BASE}/kaspersky-24/live/filesystem.squashfs" in opt.cmdline

    def test_both_iso_and_squashfs_produces_two_options(self):
        entry = self._entry_krd24(
            iso="kaspersky-24/krd-24.iso",
            squashfs="kaspersky-24/live/filesystem.squashfs",
        )
        opts = kaspersky_recipe(entry, SERVER_IP, PORT)
        assert len(opts) == 2
        modes = {o.mode for o in opts}
        assert modes == {"iso", "squashfs"}
        iso_opt = next(o for o in opts if o.mode == "iso")
        assert iso_opt.recommended is True

    def test_fallback_no_files_returns_iso_with_guessed_url(self):
        entry = self._entry_krd24()
        opts = kaspersky_recipe(entry, SERVER_IP, PORT)
        assert len(opts) == 1
        opt = opts[0]
        assert opt.mode == "iso"
        assert opt.recommended is True
        assert "fetch=" in opt.cmdline
        assert "boot=live" in opt.cmdline


# ---------------------------------------------------------------------------
# debian_recipe
# ---------------------------------------------------------------------------


class TestDebianRecipe:
    def _entry(self):
        return {
            "version": "12.9.0",
            "kernel": "debian-12.9.0/vmlinuz",
            "initrd": "debian-12.9.0/initrd.gz",
            "squashfs": None,
            "iso": None,
        }

    def test_single_netboot_option(self):
        opts = debian_recipe(self._entry(), SERVER_IP, PORT)
        assert len(opts) == 1
        opt = opts[0]
        assert opt.mode == "netboot"
        assert opt.recommended is True
        assert "ip=dhcp" in opt.cmdline


# ---------------------------------------------------------------------------
# get_recipe() — public API
# ---------------------------------------------------------------------------


class TestGetRecipe:
    def test_unknown_scenario_returns_error(self):
        result = get_recipe("unknown_os", {}, SERVER_IP, PORT)
        assert result["options"] == []
        assert "No recipe for scenario" in result["error"]

    def test_ubuntu_live_no_files_returns_error(self):
        entry = {"version": "22.04", "kernel": None, "initrd": None, "squashfs": None, "iso": None}
        result = get_recipe("ubuntu_live", entry, SERVER_IP, PORT)
        assert result["options"] == []
        assert result["error"] is not None

    def test_ubuntu_live_with_squashfs_success(self):
        entry = {
            "version": "22.04",
            "kernel": "ubuntu-22.04/casper/vmlinuz",
            "initrd": "ubuntu-22.04/casper/initrd",
            "squashfs": "ubuntu-22.04/casper/filesystem.squashfs",
            "iso": None,
        }
        result = get_recipe("ubuntu_live", entry, SERVER_IP, PORT)
        assert result["error"] is None
        assert len(result["options"]) == 1
        opt = result["options"][0]
        assert opt["recommended"] is True
        assert "fetch=" in opt["cmdline"]

    def test_result_has_all_required_keys(self):
        entry = {
            "version": "22.04",
            "kernel": "ubuntu-22.04/casper/vmlinuz",
            "initrd": "ubuntu-22.04/casper/initrd",
            "squashfs": "ubuntu-22.04/casper/filesystem.squashfs",
            "iso": None,
        }
        result = get_recipe("ubuntu_live", entry, SERVER_IP, PORT)
        opt = result["options"][0]
        for key in ("mode", "label", "kernel", "initrd", "cmdline", "recommended"):
            assert key in opt, f"Missing key: {key}"

    def test_systemrescue_scenario(self):
        entry = {
            "version": "11.01",
            "kernel": "rescue-11.01/sysresccd/boot/x86_64/vmlinuz",
            "initrd": "rescue-11.01/sysresccd/boot/x86_64/sysresccd.img",
            "squashfs": None,
            "iso": None,
        }
        result = get_recipe("systemrescue", entry, SERVER_IP, PORT)
        assert result["error"] is None
        assert result["options"][0]["mode"] == "http"

    def test_kaspersky_scenario(self):
        entry = {
            "version": "18.0",
            "kernel": "kaspersky-18.0/krd/boot/grub/k-x86_64",
            "initrd": "kaspersky-18.0/krd/boot/grub/initrd.xz",
            "squashfs": None,
            "iso": None,
        }
        result = get_recipe("kaspersky", entry, SERVER_IP, PORT)
        assert result["error"] is None

    def test_debian_netboot_scenario(self):
        entry = {
            "version": "12.9.0",
            "kernel": "debian-12.9.0/vmlinuz",
            "initrd": "debian-12.9.0/initrd.gz",
            "squashfs": None,
            "iso": None,
        }
        result = get_recipe("debian_netboot", entry, SERVER_IP, PORT)
        assert result["error"] is None
        assert result["options"][0]["mode"] == "netboot"

    def test_ubuntu_netboot_alias(self):
        """ubuntu_netboot uses the same recipe function as ubuntu_live."""
        entry = {
            "version": "22.04",
            "kernel": "ubuntu-22.04/casper/vmlinuz",
            "initrd": "ubuntu-22.04/casper/initrd",
            "squashfs": "ubuntu-22.04/casper/filesystem.squashfs",
            "iso": None,
        }
        r1 = get_recipe("ubuntu_live", entry, SERVER_IP, PORT)
        r2 = get_recipe("ubuntu_netboot", entry, SERVER_IP, PORT)
        assert r1["options"] == r2["options"]

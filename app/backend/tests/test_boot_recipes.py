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
NFS_ROOT = "/srv/nfs/http"


# ---------------------------------------------------------------------------
# ubuntu_live_recipe — Server ISO
# ---------------------------------------------------------------------------


class TestUbuntuServerRecipe:
    def _entry(self, version="22.04", squashfs=None, iso=None):
        return {
            "version": version,
            "kernel": f"ubuntu-{version}/casper/vmlinuz",
            "initrd": f"ubuntu-{version}/casper/initrd",
            "squashfs": squashfs,
            "iso": iso,
        }

    def test_server_nfs_option_when_nfs_root_configured(self):
        entry = self._entry(squashfs="ubuntu-22.04/casper/ubuntu-server-minimal.squashfs")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT, nfs_root=NFS_ROOT)
        nfs = next((o for o in opts if o.mode == "nfs"), None)
        assert nfs is not None
        assert nfs.recommended is True
        assert "netboot=nfs" in nfs.cmdline
        assert f"nfsroot={SERVER_IP}:{NFS_ROOT}/ubuntu-22.04" in nfs.cmdline
        assert "ignore_uuid" in nfs.cmdline
        assert "cloud-config-url=/dev/null" in nfs.cmdline
        assert "ip=dhcp" in nfs.cmdline

    def test_server_nfs_not_present_when_nfs_root_empty(self):
        entry = self._entry(squashfs="ubuntu-22.04/casper/ubuntu-server-minimal.squashfs")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT, nfs_root="")
        assert all(o.mode != "nfs" for o in opts)

    def test_server_iso_22_04_has_correct_ramdisk(self):
        entry = self._entry(iso="ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT)
        iso_opt = next(o for o in opts if o.mode == "iso")
        assert "ramdisk_size=1500000" in iso_opt.cmdline
        assert "root=/dev/ram0" in iso_opt.cmdline
        assert "cloud-config-url=/dev/null" in iso_opt.cmdline
        assert f"url={BASE}/ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso" in iso_opt.cmdline

    def test_server_iso_24_04_has_larger_ramdisk(self):
        entry = self._entry(version="24.04", iso="ubuntu-24.04/ubuntu-24.04-live-server-amd64.iso")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT)
        iso_opt = next(o for o in opts if o.mode == "iso")
        assert "ramdisk_size=2500000" in iso_opt.cmdline
        assert "root=/dev/ram0" in iso_opt.cmdline

    def test_server_iso_recommended_when_no_nfs(self):
        entry = self._entry(iso="ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT, nfs_root="")
        assert next(o for o in opts if o.mode == "iso").recommended is True

    def test_server_iso_not_recommended_when_nfs_available(self):
        entry = self._entry(
            squashfs="ubuntu-22.04/casper/ubuntu-server-minimal.squashfs",
            iso="ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso",
        )
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT, nfs_root=NFS_ROOT)
        assert next(o for o in opts if o.mode == "iso").recommended is False

    def test_no_squashfs_mode_for_server(self):
        """fetch= is broken on Ubuntu 22.04+ — squashfs mode must never appear."""
        entry = self._entry(
            squashfs="ubuntu-22.04/casper/ubuntu-server-minimal.squashfs",
            iso="ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso",
        )
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT, nfs_root=NFS_ROOT)
        assert all(o.mode != "squashfs" for o in opts)

    def test_server_with_nfs_and_iso_shows_both(self):
        entry = self._entry(
            squashfs="ubuntu-22.04/casper/ubuntu-server-minimal.squashfs",
            iso="ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso",
        )
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT, nfs_root=NFS_ROOT)
        modes = {o.mode for o in opts}
        assert modes == {"nfs", "iso"}
        assert next(o for o in opts if o.mode == "nfs").recommended is True
        assert next(o for o in opts if o.mode == "iso").recommended is False

    def test_no_files_returns_empty(self):
        assert ubuntu_live_recipe(self._entry(), SERVER_IP, PORT) == []


# ---------------------------------------------------------------------------
# ubuntu_live_recipe — Desktop ISO
# ---------------------------------------------------------------------------


class TestUbuntuDesktopRecipe:
    def _entry(self, version="22.04", squashfs=None, iso=None):
        return {
            "version": version,
            "kernel": f"ubuntu-{version}/casper/vmlinuz",
            "initrd": f"ubuntu-{version}/casper/initrd",
            "squashfs": squashfs,
            "iso": iso,
        }

    def test_desktop_nfs_22_04_no_cloud_init_disabled(self):
        entry = self._entry(squashfs="ubuntu-22.04/casper/filesystem.squashfs")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT, nfs_root=NFS_ROOT)
        nfs = next(o for o in opts if o.mode == "nfs")
        assert "netboot=nfs" in nfs.cmdline
        assert "ignore_uuid" in nfs.cmdline
        assert "fsck.mode=skip" in nfs.cmdline
        assert "cloud-init=disabled" not in nfs.cmdline

    def test_desktop_nfs_24_04_has_cloud_init_disabled(self):
        entry = self._entry(version="24.04", squashfs="ubuntu-24.04/casper/filesystem.squashfs")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT, nfs_root=NFS_ROOT)
        nfs = next(o for o in opts if o.mode == "nfs")
        assert "cloud-init=disabled" in nfs.cmdline

    def test_desktop_iso_22_04_cmdline(self):
        entry = self._entry(iso="ubuntu-22.04/ubuntu-22.04-desktop-amd64.iso")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT)
        iso_opt = next(o for o in opts if o.mode == "iso")
        assert "boot=casper" in iso_opt.cmdline
        assert "cloud-config-url=/dev/null" in iso_opt.cmdline
        assert "cloud-init=disabled" not in iso_opt.cmdline
        assert "root=/dev/ram0" not in iso_opt.cmdline

    def test_desktop_iso_24_04_has_cloud_init_disabled(self):
        entry = self._entry(version="24.04", iso="ubuntu-24.04/ubuntu-24.04-desktop-amd64.iso")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT)
        iso_opt = next(o for o in opts if o.mode == "iso")
        assert "cloud-init=disabled" in iso_opt.cmdline

    def test_no_squashfs_mode_for_desktop(self):
        """fetch= is broken on Ubuntu 22.04+ — squashfs mode must never appear."""
        entry = self._entry(squashfs="ubuntu-22.04/casper/filesystem.squashfs")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT)
        assert all(o.mode != "squashfs" for o in opts)

    def test_kernel_and_initrd_propagated(self):
        entry = self._entry(squashfs="ubuntu-22.04/casper/filesystem.squashfs")
        opts = ubuntu_live_recipe(entry, SERVER_IP, PORT, nfs_root=NFS_ROOT)
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
        assert opts[0].mode == "http"
        assert opts[0].recommended is True

    def test_cmdline_contains_base_url_and_ip_dhcp(self):
        opts = systemrescue_recipe(self._entry(), SERVER_IP, PORT)
        assert f"archiso_http_srv={BASE}/rescue-11.01/" in opts[0].cmdline
        assert "archisobasedir=sysresccd" in opts[0].cmdline
        assert "ip=dhcp" in opts[0].cmdline


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

    def test_krd18_produces_netboot_option(self):
        opts = kaspersky_recipe(self._entry_krd18(), SERVER_IP, PORT)
        assert len(opts) == 1
        assert opts[0].mode == "netboot"
        assert opts[0].recommended is True

    def test_krd18_cmdline(self):
        cmdline = kaspersky_recipe(self._entry_krd18(), SERVER_IP, PORT)[0].cmdline
        assert f"netboot={BASE}/kaspersky-18/krd/" in cmdline
        assert "dostartx" in cmdline
        assert "net.ifnames=0" in cmdline
        assert "initrd=initrd.xz" in cmdline

    def test_krd18_kernel_and_initrd_preserved(self):
        opts = kaspersky_recipe(self._entry_krd18(), SERVER_IP, PORT)
        assert opts[0].kernel == "kaspersky-18/krd/boot/grub/k-x86_64"
        assert opts[0].initrd == "kaspersky-18/krd/boot/grub/initrd.xz"

    def test_krd24_iso_recommended(self):
        opts = kaspersky_recipe(self._entry_krd24(iso="kaspersky-24/krd-24.iso"), SERVER_IP, PORT)
        assert opts[0].mode == "iso"
        assert opts[0].recommended is True
        assert f"fetch={BASE}/kaspersky-24/krd-24.iso" in opts[0].cmdline
        assert "boot=live" in opts[0].cmdline

    def test_krd24_squashfs_option(self):
        opts = kaspersky_recipe(
            self._entry_krd24(squashfs="kaspersky-24/live/filesystem.squashfs"), SERVER_IP, PORT
        )
        assert opts[0].mode == "squashfs"
        assert f"fetch={BASE}/kaspersky-24/live/filesystem.squashfs" in opts[0].cmdline

    def test_krd24_both_iso_and_squashfs(self):
        opts = kaspersky_recipe(
            self._entry_krd24(
                iso="kaspersky-24/krd-24.iso",
                squashfs="kaspersky-24/live/filesystem.squashfs",
            ),
            SERVER_IP,
            PORT,
        )
        assert {o.mode for o in opts} == {"iso", "squashfs"}
        assert next(o for o in opts if o.mode == "iso").recommended is True

    def test_krd24_fallback_no_files(self):
        opts = kaspersky_recipe(self._entry_krd24(), SERVER_IP, PORT)
        assert len(opts) == 1
        assert opts[0].mode == "iso"
        assert "fetch=" in opts[0].cmdline


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
        assert opts[0].mode == "netboot"
        assert opts[0].recommended is True
        assert "ip=dhcp" in opts[0].cmdline


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

    def test_ubuntu_server_with_nfs_returns_nfs_and_iso(self):
        entry = {
            "version": "22.04",
            "kernel": "ubuntu-22.04/casper/vmlinuz",
            "initrd": "ubuntu-22.04/casper/initrd",
            "squashfs": "ubuntu-22.04/casper/ubuntu-server-minimal.squashfs",
            "iso": "ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso",
        }
        result = get_recipe("ubuntu_live", entry, SERVER_IP, PORT, nfs_root=NFS_ROOT)
        assert result["error"] is None
        modes = {o["mode"] for o in result["options"]}
        assert "nfs" in modes
        assert "iso" in modes
        assert "squashfs" not in modes
        assert next(o for o in result["options"] if o["mode"] == "nfs")["recommended"] is True

    def test_ubuntu_server_no_nfs_returns_iso_recommended(self):
        entry = {
            "version": "22.04",
            "kernel": "ubuntu-22.04/casper/vmlinuz",
            "initrd": "ubuntu-22.04/casper/initrd",
            "squashfs": "ubuntu-22.04/casper/ubuntu-server-minimal.squashfs",
            "iso": "ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso",
        }
        result = get_recipe("ubuntu_live", entry, SERVER_IP, PORT, nfs_root="")
        assert result["error"] is None
        assert len(result["options"]) == 1
        assert result["options"][0]["mode"] == "iso"
        assert result["options"][0]["recommended"] is True

    def test_result_has_all_required_keys(self):
        entry = {
            "version": "22.04",
            "kernel": "ubuntu-22.04/casper/vmlinuz",
            "initrd": "ubuntu-22.04/casper/initrd",
            "squashfs": None,
            "iso": "ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso",
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

    def test_ubuntu_netboot_alias_same_as_ubuntu_live(self):
        entry = {
            "version": "22.04",
            "kernel": "ubuntu-22.04/casper/vmlinuz",
            "initrd": "ubuntu-22.04/casper/initrd",
            "squashfs": None,
            "iso": "ubuntu-22.04/ubuntu-22.04-live-server-amd64.iso",
        }
        r1 = get_recipe("ubuntu_live", entry, SERVER_IP, PORT)
        r2 = get_recipe("ubuntu_netboot", entry, SERVER_IP, PORT)
        assert r1["options"] == r2["options"]

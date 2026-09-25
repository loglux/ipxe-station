"""Downloadable tools (Rescuezilla, ShredOS): versions, checksums, disk scan and boot recipes."""

import contextlib
import hashlib

import pytest
from fastapi.testclient import TestClient

import app.backend.tool_catalog as tc
import app.routes.assets as assets_routes
from app.backend.boot_recipes import get_recipe, rescuezilla_recipe, shredos_recipe
from app.main import app
from app.routes.state import _scan_distro_versions

client = TestClient(app)

RZ_ASSETS = [
    {
        "name": "rescuezilla-2.6.2-64bit.questing.iso",
        "size": 1_666_000_000,
        "browser_download_url": "https://x/q.iso",
    },
    {
        "name": "rescuezilla-2.6.2-64bit.noble.iso",
        "size": 1_594_000_000,
        "browser_download_url": "https://x/n.iso",
    },
    {
        "name": "rescuezilla_2.6.2-1_all.deb",
        "size": 1_000_000,
        "browser_download_url": "https://x/a.deb",
    },
    {"name": "SHA256SUM", "size": 500, "browser_download_url": "https://x/SHA256SUM"},
]
RZ_SUMS = (
    f"{'a' * 64}  rescuezilla-2.6.2-64bit.noble.iso\n"
    f"{'b' * 64}  rescuezilla-2.6.2-64bit.questing.iso\n"
)

SHRED_ASSETS = [
    {
        "name": "shredos-2025.11_31_x86-64_v0.42_20260716.iso",
        "size": 361_000_000,
        "browser_download_url": "https://x/full.iso",
    },
    {
        "name": "shredos-2025.11_31_x86-64_v0.42_20260716.iso.sha1",
        "size": 90,
        "browser_download_url": "https://x/full.sha1",
    },
    {
        "name": "shredos-2025.11_31_x86-64_v0.42_20260716_lite.iso",
        "size": 108_000_000,
        "browser_download_url": "https://x/lite.iso",
    },
    {
        "name": "shredos-2025.11_31_x86-64_v0.42_20260716_plus-partition.iso",
        "size": 413_000_000,
        "browser_download_url": "https://x/plus.iso",
    },
    {
        "name": "shredos-2025.11_31_i686_v0.42_20260716_lite.iso",
        "size": 104_000_000,
        "browser_download_url": "https://x/i686.iso",
    },
]


@pytest.fixture
def github(monkeypatch):
    """Serve fake GitHub releases; a test can replace `releases` or set it to {} to go offline."""
    releases = {
        "rescuezilla/rescuezilla": {"assets": RZ_ASSETS},
        "PartialVolume/shredos.x86_64": {"assets": SHRED_ASSETS},
    }
    texts = {
        "https://x/SHA256SUM": RZ_SUMS,
        "https://x/full.sha1": f"{'c' * 40}  shredos-2025.11_31_x86-64_v0.42_20260716.iso\n",
    }
    monkeypatch.setattr(tc, "_latest_release", lambda repo: releases.get(repo))
    monkeypatch.setattr(tc, "_download_text", lambda url: texts.get(url, ""))
    return releases


def test_checksum_files_are_parsed_in_both_formats():
    text = f"{'A' * 64}  one.iso\n{'b' * 40} *two.iso\nnot a hash line\n"

    assert tc.parse_checksum_file(text) == {"one.iso": "a" * 64, "two.iso": "b" * 40}


def test_rescuezilla_lists_the_ubuntu_lts_build_first_with_its_checksum(github):
    versions = tc.rescuezilla_versions()

    assert [v["version"] for v in versions] == ["2.6.2", "2.6.2-questing"]
    noble = versions[0]
    assert noble["recommended"] and noble["dest_folder"] == "rescuezilla-2.6.2"
    assert noble["checksum"] == f"sha256:{'a' * 64}"
    assert noble["iso_name"] == "rescuezilla-2.6.2-64bit.noble.iso"
    assert "Ubuntu 24.04 LTS" in noble["name"] and noble["size_est"] == "~1.6 GB"


def test_shredos_offers_full_and_lite_but_not_usb_or_32_bit_images(github):
    versions = tc.shredos_versions()

    assert [v["version"] for v in versions] == ["0.42", "0.42-lite"]
    full, lite = versions
    assert full["recommended"] and full["dest_folder"] == "shredos-0.42"
    assert full["checksum"] == f"sha1:{'c' * 40}"
    assert "checksum" not in lite  # no .sha1 published for it in this fake release
    assert lite["dest_folder"] == "shredos-0.42-lite" and "512 MB" in lite["notes"]
    assert "erases disks" in full["warning"]


def test_known_good_releases_are_offered_when_github_cannot_be_reached(github):
    github.clear()

    rescuezilla = tc.rescuezilla_versions()
    shredos = tc.shredos_versions()

    assert (
        rescuezilla[0]["checksum"].startswith("sha256:") and len(rescuezilla[0]["checksum"]) == 71
    )
    assert [v["version"] for v in shredos] == ["0.42", "0.42-lite"]
    assert all(v["checksum"].startswith("sha1:") for v in shredos)


def test_tools_endpoint_lists_every_tool_with_versions(github):
    data = client.get("/api/assets/tools").json()

    assert [t["id"] for t in data["tools"]] == ["rescuezilla", "shredos"]
    assert all(t["versions"] for t in data["tools"])
    assert data["tools"][1]["warning"]
    assert client.get("/api/assets/versions/shredos").json()["versions"][0]["version"] == "0.42"


# ---------------------------------------------------------------------------
# Download with a checksum
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body
        self.headers = {"content-length": str(len(body))}

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=8192):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]


@pytest.fixture
def download_env(tmp_path, monkeypatch):
    body = b"pretend this is an ISO" * 1000

    @contextlib.contextmanager
    def fake_request(method, url, **kwargs):
        yield _FakeResponse(body)

    monkeypatch.setattr(assets_routes, "HTTP_ROOT", tmp_path)
    monkeypatch.setattr(assets_routes, "assert_public_http_url", lambda url: None)
    monkeypatch.setattr(assets_routes, "safe_request", fake_request)
    return tmp_path, body


def test_download_with_a_matching_checksum_is_kept(download_env):
    root, body = download_env
    digest = hashlib.sha256(body).hexdigest()

    resp = client.post(
        "/api/assets/download",
        json={
            "url": "https://example.org/tool.bin",
            "dest": "tool-1/tool.bin",
            "checksum": f"sha256:{digest}",
        },
    )

    assert resp.status_code == 200
    assert (root / "tool-1" / "tool.bin").read_bytes() == body


def test_download_with_a_wrong_checksum_is_discarded(download_env):
    root, _ = download_env

    resp = client.post(
        "/api/assets/download",
        json={
            "url": "https://example.org/tool.bin",
            "dest": "tool-2/tool.bin",
            "checksum": f"sha1:{'0' * 40}",
        },
    )

    assert resp.status_code == 500 and "Checksum mismatch" in resp.json()["detail"]
    assert not (root / "tool-2" / "tool.bin").exists()
    assert not list((root / "tool-2").glob("*.tmp"))


@pytest.mark.parametrize("bad", ["md5:" + "0" * 32, "sha256:xyz", "sha256:" + "0" * 10, "nonsense"])
def test_malformed_checksums_are_rejected_before_downloading(download_env, bad):
    resp = client.post(
        "/api/assets/download",
        json={"url": "https://example.org/tool.bin", "dest": "tool-3/tool.bin", "checksum": bad},
    )

    assert resp.status_code == 400


def test_download_without_a_checksum_still_works(download_env):
    root, body = download_env

    resp = client.post(
        "/api/assets/download", json={"url": "https://example.org/x.bin", "dest": "tool-4/x.bin"}
    )

    assert resp.status_code == 200 and (root / "tool-4" / "x.bin").read_bytes() == body


# ---------------------------------------------------------------------------
# Disk scan and boot recipes
# ---------------------------------------------------------------------------


def _touch(root, *parts):
    path = root.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def test_scan_recognises_the_rescuezilla_and_shredos_layouts(tmp_path):
    for name in ("vmlinuz", "initrd.lz", "filesystem.squashfs"):
        _touch(tmp_path, "rescuezilla-2.6.2", "casper", name)
    _touch(tmp_path, "rescuezilla-2.6.2", "rescuezilla-2.6.2-64bit.noble.iso")
    _touch(tmp_path, "shredos-0.42", "boot", "bzImage")

    (rz,) = _scan_distro_versions("rescuezilla", tmp_path)
    (shred,) = _scan_distro_versions("shredos", tmp_path)

    assert rz["kernel"] == "rescuezilla-2.6.2/casper/vmlinuz"
    assert rz["initrd"] == "rescuezilla-2.6.2/casper/initrd.lz"
    assert rz["squashfs"].endswith("filesystem.squashfs") and rz["iso"].endswith(".iso")
    assert shred["kernel"] == "shredos-0.42/boot/bzImage" and shred["initrd"] is None
    # "rescue-*" (SystemRescue) must not pick up "rescuezilla-*"
    assert _scan_distro_versions("rescue", tmp_path) == []


RZ_ENTRY = {
    "version": "2.6.2",
    "kernel": "rescuezilla-2.6.2/casper/vmlinuz",
    "initrd": "rescuezilla-2.6.2/casper/initrd.lz",
    "iso": "rescuezilla-2.6.2/rescuezilla-2.6.2-64bit.noble.iso",
}


def test_rescuezilla_prefers_nfs_and_pins_the_boot_nic():
    opts = rescuezilla_recipe(RZ_ENTRY, "10.0.0.1", 9021, nfs_root="/srv/http")

    assert [o.mode for o in opts] == ["nfs", "nfs-safe", "iso"]
    nfs = opts[0]
    assert nfs.recommended and not opts[2].recommended
    assert "netboot=nfs nfsroot=10.0.0.1:/srv/http/rescuezilla-2.6.2" in nfs.cmdline
    assert "noprompt" in nfs.cmdline and "BOOTIF=01-${net0/mac:hexhyp}" in nfs.cmdline
    assert "nomodeset" in opts[1].cmdline and "nomodeset" not in nfs.cmdline
    assert (
        "url=http://10.0.0.1:9021/http/rescuezilla-2.6.2/rescuezilla-2.6.2-64bit.noble.iso"
        in opts[2].cmdline
    )


def test_rescuezilla_falls_back_to_the_iso_without_an_nfs_export():
    opts = rescuezilla_recipe(RZ_ENTRY, "10.0.0.1", 9021, nfs_root="")

    assert [o.mode for o in opts] == ["iso"] and opts[0].recommended
    assert rescuezilla_recipe({"version": "x"}, "10.0.0.1", 9021) == []  # nothing bootable found


def test_shredos_is_one_kernel_without_an_initrd():
    result = get_recipe(
        "shredos", {"version": "0.42", "kernel": "shredos-0.42/boot/bzImage"}, "10.0.0.1", 9021
    )

    assert result["error"] is None
    first, safe = result["options"]
    assert first["kernel"] == "shredos-0.42/boot/bzImage" and first["initrd"] == ""
    assert first["cmdline"] == "console=tty3 loglevel=3" and first["recommended"]
    assert safe["cmdline"].endswith("nomodeset")
    assert shredos_recipe({"version": "0.42"}, "10.0.0.1", 9021) == []


def test_boot_recipe_endpoint_and_catalog_know_the_new_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(assets_routes, "HTTP_ROOT", tmp_path)
    _touch(tmp_path, "shredos-0.42", "boot", "bzImage")

    catalog = client.get("/api/assets/catalog").json()
    recipe = client.get(
        "/api/assets/boot-recipe", params={"version_path": "shredos-0.42", "scenario": "shredos"}
    ).json()

    assert (
        catalog["shredos"][0]["kernel"] == "shredos-0.42/boot/bzImage"
        and catalog["rescuezilla"] == []
    )
    assert recipe["error"] is None and recipe["options"][0]["initrd"] == ""

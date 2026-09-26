"""Firmware for Kaspersky Rescue Disk: the catalog, the cached release, archives and reports."""

import hashlib
import io
import subprocess
import tarfile
import time

import pytest
from fastapi.testclient import TestClient

import app.backend.krd_display as kd
import app.backend.krd_firmware as fw
from app.backend.krd_maintenance import KrdError
from app.main import app
from app.routes import state
from app.routes.kaspersky import MAX_REPORT_BYTES

client = TestClient(app)

# What the Dell Latitude 5530 printed (shortened): the driver walks the API versions downwards.
DMESG = """
[    7.283175] platform regulatory.0: firmware: direct-loading firmware regulatory.db
[    7.395672] iwlwifi 0000:00:14.3: firmware: failed to load iwlwifi-so-a0-gf-a0-72.ucode (-2)
[    7.398935] firmware_class: See https://wiki.debian.org/Firmware for information about missing firmware
[    7.399965] iwlwifi 0000:00:14.3: Direct firmware load for iwlwifi-so-a0-gf-a0-72.ucode failed with error -2
[    7.401826] iwlwifi 0000:00:14.3: firmware: failed to load iwlwifi-so-a0-gf-a0-71.ucode (-2)
[    7.483137] iwlwifi 0000:00:14.3: Direct firmware load for iwlwifi-so-a0-gf-a0-39.ucode failed with error -2
[    7.843610] bluetooth hci0: firmware: failed to load intel/ibt-0040-0041.sfi (-2)
[    7.847842] Bluetooth: hci0: Failed to load Intel firmware file intel/ibt-0040-0041.sfi (-2)
"""  # noqa: E501

WHENCE = (
    """
Driver: iwlwifi - Intel Wireless Wifi

File: iwlwifi-so-a0-gf-a0-71.ucode
File: iwlwifi-so-a0-gf-a0-72.ucode
File: iwlwifi-so-a0-gf-a0.pnvm
File: iwlwifi-cc-a0-72.ucode
File: iwlwifi-ty-a0-gf-a0-72.ucode
File: iwlwifi-ty-a0-gf-a0.pnvm
File: iwlwifi-QuZ-a0-hr-b0-72.ucode
"""
    + "".join(f"File: iwlwifi-chip{i}-a0-72.ucode\n" for i in range(20))
    + """

--------------------------------------------------------------------------

Driver: btusb -- Intel Bluetooth

File: intel/ibt-0040-0041.sfi
File: intel/ibt-0040-0041.ddc
Link: intel/ibt-0040-4150.sfi -> ibt-0040-0041.sfi

--------------------------------------------------------------------------

Driver: snd-korg1212 -- Korg 1212 IO audio device

File: korg/k1212.dsp

--------------------------------------------------------------------------

Driver: ti_usb_3410_5052 -- USB TI 3410/5052 serial device
File: ti_3410.fw

Driver: ti_usb_3410_5052 -- Multi-Tech USB cell modems
File: mts_cdma.fw

--------------------------------------------------------------------------

Driver: bigradio -- A driver with many files
"""
    + "".join(f"File: big/radio_{i}.bin\n" for i in range(30))
)


def make_release(root="linux-firmware-20230210"):
    """A gzip tar shaped like the official release, with a WHENCE and a few files and links."""
    contents = {
        "WHENCE": WHENCE.encode(),
        "iwlwifi-so-a0-gf-a0-71.ucode": b"71" * 100,
        "iwlwifi-so-a0-gf-a0-72.ucode": b"72" * 100,
        "iwlwifi-so-a0-gf-a0.pnvm": b"pnvm",
        "iwlwifi-cc-a0-72.ucode": b"cc" * 50,
        "iwlwifi-ty-a0-gf-a0-72.ucode": b"ty" * 50,
        "iwlwifi-ty-a0-gf-a0.pnvm": b"typnvm",
        "iwlwifi-QuZ-a0-hr-b0-72.ucode": b"quz" * 50,
        "intel/ibt-0040-0041.sfi": b"sfi-data",
        "intel/ibt-0040-0041.ddc": b"ddc",
        "korg/k1212.dsp": b"dsp",
        "ti_3410.fw": b"ti",
        "mts_cdma.fw": b"mts",
        "unlisted/extra.bin": b"nobody documents me",
    }
    contents.update({f"big/radio_{i}.bin": f"radio{i}".encode() for i in range(30)})
    contents.update({f"iwlwifi-chip{i}-a0-72.ucode": b"chip" for i in range(20)})
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in contents.items():
            info = tarfile.TarInfo(f"{root}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo(f"{root}/intel/ibt-0040-4150.sfi")
        link.type, link.linkname = tarfile.SYMTYPE, "ibt-0040-0041.sfi"
        tar.addfile(link)
        dangling = tarfile.TarInfo(f"{root}/intel/ibt-gone.sfi")
        dangling.type, dangling.linkname = tarfile.SYMTYPE, "missing.sfi"
        tar.addfile(dangling)
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, text="", content=b"", status=200):
        self.text, self._content, self.status_code = text, content, status
        self.headers = {"Content-Length": str(len(content))}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise fw.requests.HTTPError(str(self.status_code))

    def iter_content(self, size):
        yield self._content

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_kernel_org(monkeypatch, release=None, digest=None):
    release = release if release is not None else make_release()
    digest = digest or hashlib.sha256(release).hexdigest()

    def get(url, **kwargs):
        assert kwargs.get("headers") == fw.HEADERS  # kernel.org refuses the default agent
        if url.endswith("sha256sums.asc"):
            return FakeResponse(f"{digest}  {fw.FULL_ARCHIVE}\n")
        return FakeResponse(content=release)

    monkeypatch.setattr(fw.requests, "get", get)
    monkeypatch.setattr(fw.shutil, "disk_usage", lambda p: type("U", (), {"free": 10**11})())


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """A cache holding the downloaded fake release, and the catalog made from it."""
    fake_kernel_org(monkeypatch)
    root = tmp_path / "_src" / "linux-firmware"
    fw.download_source(root)
    return root


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "http" / "kaspersky-24"
    (d / "live" / "KRD").mkdir(parents=True)
    (d / "live" / "KRD" / "30-bases.srm").write_bytes(b"x")
    return d


def item_named(cache_root, text):
    matches = [i for i in fw.load_catalog(cache_root)["items"] if text.lower() in i["name"].lower()]
    assert matches, text
    return matches[0]


# --- reading dmesg ------------------------------------------------------------------


def test_parse_folds_wifi_versions_into_one_entry():
    found = {item["name"]: item for item in fw.parse_missing_firmware(DMESG)}
    assert set(found) == {"iwlwifi-so-a0-gf-a0-72.ucode", "intel/ibt-0040-0041.sfi"}
    wifi = found["iwlwifi-so-a0-gf-a0-72.ucode"]
    assert wifi["alternatives"] == ["iwlwifi-so-a0-gf-a0-71.ucode", "iwlwifi-so-a0-gf-a0-39.ucode"]
    assert wifi["companions"] == ["iwlwifi-so-a0-gf-a0.pnvm"]
    assert found["intel/ibt-0040-0041.sfi"]["companions"] == ["intel/ibt-0040-0041.ddc"]


def test_parse_ignores_successful_loads_and_junk():
    assert fw.parse_missing_firmware("firmware: direct-loading firmware regulatory.db") == []
    assert fw.parse_missing_firmware("") == []
    assert fw.parse_missing_firmware("Direct firmware load for ../../etc/passwd failed") == []


# --- the catalog --------------------------------------------------------------------


def test_whence_is_read_into_devices_with_their_files():
    blocks = fw.parse_whence(WHENCE)
    by_name = {b["name"]: b for b in blocks}
    assert by_name["iwlwifi"]["description"] == "Intel Wireless Wifi"
    assert "iwlwifi-cc-a0-72.ucode" in by_name["iwlwifi"]["files"]
    assert by_name["btusb"]["links"] == ["intel/ibt-0040-4150.sfi"]


def test_catalog_has_one_entry_per_device_and_merges_repeated_ones(cache):
    names = [i["name"] for i in fw.load_catalog(cache)["items"]]
    assert "snd-korg1212" in names
    assert names.count("ti_usb_3410_5052") == 1
    merged = item_named(cache, "ti_usb_3410_5052")
    assert sorted(merged["files"]) == ["mts_cdma.fw", "ti_3410.fw"]


def test_files_nobody_documents_stay_out_of_the_catalog_but_can_be_named(cache):
    catalog = fw.load_catalog(cache)
    assert not any("unlisted/extra.bin" in i["files"] for i in catalog["items"])
    assert "unlisted/extra.bin" in catalog["all_files"]


def test_a_device_with_many_files_is_split_by_chip_and_named_plainly(cache):
    wifi = [
        i for i in fw.load_catalog(cache)["items"] if i["name"].endswith("(iwlwifi so-a0-gf-a0)")
    ]
    assert len(wifi) == 1 and wifi[0]["name"].startswith("Wi-Fi 6E AX211")
    assert sorted(wifi[0]["files"]) == [
        "iwlwifi-so-a0-gf-a0-71.ucode",
        "iwlwifi-so-a0-gf-a0-72.ucode",
        "iwlwifi-so-a0-gf-a0.pnvm",
    ]
    assert wifi[0]["category"] == "wifi"
    ty = item_named(cache, "AX210")
    assert ".pnvm" in " ".join(ty["files"])


def test_a_device_with_few_files_stays_one_entry(cache):
    assert item_named(cache, "btusb")["count"] == 3  # two files and a link


def test_links_are_followed_and_broken_ones_dropped(cache):
    catalog = fw.load_catalog(cache)
    assert catalog["links"] == {"intel/ibt-0040-4150.sfi": "intel/ibt-0040-0041.sfi"}
    assert "intel/ibt-gone.sfi" not in catalog["all_files"]


def test_categories(cache):
    by_name = {i["name"]: i["category"] for i in fw.load_catalog(cache)["items"]}
    assert by_name["btusb"] == "bluetooth"
    assert by_name["snd-korg1212"] == "audio"
    assert by_name["ti_usb_3410_5052"] == "other"


def test_sizes_count_what_the_files_weigh(cache):
    assert item_named(cache, "AX211")["size"] == 200 + 200 + 4  # 71, 72 and the pnvm


def test_items_covering_finds_the_entries_for_missing_files(cache):
    wanted = [m["name"] for m in fw.parse_missing_firmware(DMESG)]
    ids = fw.items_covering(cache, wanted + ["iwlwifi-so-a0-gf-a0-71.ucode"])
    assert set(ids) == {item_named(cache, "AX211")["id"], item_named(cache, "btusb")["id"]}


# --- the cached release --------------------------------------------------------------


def test_download_verifies_and_makes_the_catalog(tmp_path, monkeypatch):
    fake_kernel_org(monkeypatch)
    root = tmp_path / "cache"
    seen = []
    result = fw.download_source(root, lambda done, total: seen.append((done, total)))
    assert result["items"] > 5 and seen
    state_ = fw.source_state(root)
    assert state_["downloaded"] and state_["items"] == result["items"]
    assert not list(root.glob("*.download"))


def test_a_download_that_does_not_match_the_checksum_is_discarded(tmp_path, monkeypatch):
    fake_kernel_org(monkeypatch, digest="0" * 64)
    with pytest.raises(KrdError, match="checksum"):
        fw.download_source(tmp_path / "cache")
    assert fw.source_state(tmp_path / "cache")["downloaded"] is False
    assert not list((tmp_path / "cache").glob("*"))


def test_a_release_without_a_readable_whence_is_refused(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("linux-firmware-20230210/a.bin")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"a"))
    fake_kernel_org(monkeypatch, release=buffer.getvalue())
    with pytest.raises(KrdError):
        fw.download_source(tmp_path / "cache")
    assert not fw.source_state(tmp_path / "cache")["downloaded"]


def test_removing_the_cache(cache):
    assert fw.remove_source(cache) is True
    assert fw.source_state(cache)["downloaded"] is False
    assert fw.remove_source(cache) is False


# --- building the archive -------------------------------------------------------------


def unpack(folder, tmp_path):
    out = tmp_path / "unpacked"
    out.mkdir(exist_ok=True)
    with tarfile.open(folder / "linux-firmware-custom.tar.gz") as tar:
        tar.extractall(out, filter="data")
    return out / "linux-firmware-custom"


def test_archive_has_the_layout_the_boot_hook_needs(cache, folder, tmp_path):
    item = item_named(cache, "AX211")
    result = fw.build_custom_firmware(folder, cache, [item["id"]])
    assert result["archive"] == "linux-firmware-custom.tar.gz" and len(result["added"]) == 3
    root = unpack(folder, tmp_path)
    assert (root / "copy-firmware.sh").stat().st_mode & 0o111
    assert (root / "files" / "iwlwifi-so-a0-gf-a0-72.ucode").read_bytes() == b"72" * 100


def test_the_installer_script_copies_everything_into_the_target(cache, folder, tmp_path):
    fw.build_custom_firmware(folder, cache, [item_named(cache, "btusb")["id"]])
    root = unpack(folder, tmp_path)
    target = tmp_path / "usr-lib-firmware"
    subprocess.run([str(root / "copy-firmware.sh"), str(target)], check=True)
    assert (target / "intel" / "ibt-0040-0041.sfi").read_bytes() == b"sfi-data"


def test_a_link_becomes_a_real_copy_of_its_target(cache, folder, tmp_path):
    fw.build_custom_firmware(folder, cache, [item_named(cache, "btusb")["id"]])
    files = unpack(folder, tmp_path) / "files" / "intel"
    assert (files / "ibt-0040-4150.sfi").read_bytes() == b"sfi-data"
    assert not (files / "ibt-0040-4150.sfi").is_symlink()


def test_named_files_come_from_the_release_with_fallbacks_and_companions(cache, folder, tmp_path):
    result = fw.build_custom_firmware(
        folder,
        cache,
        [],
        [
            {
                "name": "iwlwifi-so-a0-gf-a0-73.ucode",
                "alternatives": ["iwlwifi-so-a0-gf-a0-72.ucode"],
            },
            {"name": "unlisted/extra.bin"},
            {"name": "nowhere.bin"},
        ],
    )
    assert set(result["added"]) == {
        "iwlwifi-so-a0-gf-a0-72.ucode",
        "iwlwifi-so-a0-gf-a0.pnvm",  # companion of the Wi-Fi file
        "unlisted/extra.bin",
    }
    assert result["skipped"] == ["nowhere.bin"]  # a missing companion is not worth a warning


def test_devices_and_named_files_can_be_mixed_without_repeats(cache, folder):
    item = item_named(cache, "AX211")
    result = fw.build_custom_firmware(
        folder, cache, [item["id"]], [{"name": "iwlwifi-so-a0-gf-a0-72.ucode"}]
    )
    assert result["added"].count("iwlwifi-so-a0-gf-a0-72.ucode") == 1


def test_unknown_entry_and_empty_choice_are_refused(cache, folder):
    with pytest.raises(KrdError, match="Unknown"):
        fw.build_custom_firmware(folder, cache, ["no-such-item"])
    with pytest.raises(KrdError, match="at least one"):
        fw.build_custom_firmware(folder, cache, [], [])
    assert fw.firmware_archives(folder) == []


@pytest.mark.parametrize("bad", ["../etc/passwd", "/abs/path", "a b.bin", "x/../../y", ""])
def test_bad_names_are_refused(cache, folder, bad):
    with pytest.raises(KrdError):
        fw.build_custom_firmware(folder, cache, [], [{"name": bad}])


def test_nothing_found_leaves_no_archive_behind(cache, folder):
    with pytest.raises(KrdError):
        fw.build_custom_firmware(folder, cache, [], [{"name": "nowhere.bin"}])
    assert fw.firmware_archives(folder) == [] and not list(folder.glob("*.tmp"))


def test_devices_need_the_release_but_named_files_do_not(tmp_path, folder, monkeypatch):
    empty = tmp_path / "empty-cache"
    with pytest.raises(KrdError, match="Download the firmware release"):
        fw.build_custom_firmware(folder, empty, ["anything"])
    monkeypatch.setattr(fw, "_fetch_remote_file", lambda path: b"data" if path == "a.bin" else None)
    result = fw.build_custom_firmware(folder, empty, [], [{"name": "a.bin"}, {"name": "b.bin"}])
    assert result["added"] == ["a.bin"] and result["skipped"] == ["b.bin"]


def test_only_one_firmware_archive_may_remain(cache, folder):
    """KRD panics at boot when the disk root holds two linux-firmware archives."""
    (folder / "linux-firmware-20230210.tar.gz").write_bytes(b"full")
    result = fw.build_custom_firmware(folder, cache, [item_named(cache, "btusb")["id"]])
    assert result["replaced"] == ["linux-firmware-20230210.tar.gz"]
    assert [a.name for a in fw.firmware_archives(folder)] == ["linux-firmware-custom.tar.gz"]
    assert fw.firmware_state(folder)["kind"] == "custom"


def test_full_set_comes_from_the_cache_without_downloading_again(cache, folder, monkeypatch):
    monkeypatch.setattr(fw.requests, "get", lambda *a, **k: pytest.fail("must not download"))
    (folder / "linux-firmware-custom.tar.gz").write_bytes(b"small")
    result = fw.install_full_firmware(folder, cache)
    assert result["archive"] == fw.FULL_ARCHIVE and result["replaced"] == [
        "linux-firmware-custom.tar.gz"
    ]
    assert (folder / fw.FULL_ARCHIVE).read_bytes() == (cache / fw.FULL_ARCHIVE).read_bytes()
    assert fw.firmware_state(folder)["kind"] == "full"


def test_full_set_downloads_the_release_first_when_it_is_not_cached(tmp_path, folder, monkeypatch):
    fake_kernel_org(monkeypatch)
    result = fw.install_full_firmware(folder, tmp_path / "cache")
    assert (folder / result["archive"]).exists() and fw.source_state(tmp_path / "cache")[
        "downloaded"
    ]


# --- machine reports and the API -----------------------------------------------------


@pytest.fixture
def api(tmp_path, monkeypatch, cache, folder):
    monkeypatch.setattr(state, "HTTP_ROOT", folder.parent)
    monkeypatch.setattr(state, "BASE_ROOT", cache.parent.parent)
    monkeypatch.setattr(state, "IPXE_ROOT", tmp_path)
    return folder


def wait_for(name, kind="firmware"):
    for _ in range(100):
        job = client.get(f"/api/kaspersky/{name}/jobs/{kind}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_api_source_lists_the_catalog(api):
    got = client.get("/api/kaspersky/firmware-source").json()
    assert got["downloaded"] is True and got["tag"] == fw.FIRMWARE_TAG
    assert any(i["name"] == "btusb" for i in got["catalog"])
    assert all("files" not in i for i in got["catalog"])  # the list stays small
    assert got["categories"]["wifi"] == "Wi-Fi"


def test_api_source_download_and_remove(tmp_path, monkeypatch):
    fake_kernel_org(monkeypatch)
    monkeypatch.setattr(state, "BASE_ROOT", tmp_path)
    assert client.get("/api/kaspersky/firmware-source").json()["downloaded"] is False
    assert client.post("/api/kaspersky/firmware-source/download").json() == {"started": True}
    for _ in range(100):
        job = client.get("/api/kaspersky/firmware-source/job").json()
        if job["state"] != "running":
            break
        time.sleep(0.05)
    assert job["state"] == "done"
    assert client.get("/api/kaspersky/firmware-source").json()["downloaded"] is True
    assert client.delete("/api/kaspersky/firmware-source").json() == {"removed": True}


def test_api_scan_says_which_entries_fix_it(api):
    got = client.post("/api/kaspersky/kaspersky-24/firmware/scan", json={"text": DMESG}).json()
    assert {m["name"] for m in got["missing"]} == {
        "iwlwifi-so-a0-gf-a0-72.ucode",
        "intel/ibt-0040-0041.sfi",
    }
    assert len(got["items"]) == 2


def test_api_build_from_entries_and_remove(api):
    ids = [
        i["id"]
        for i in client.get("/api/kaspersky/firmware-source").json()["catalog"]
        if i["name"] == "btusb"
    ]
    body = {"items": ids, "files": []}
    assert client.post("/api/kaspersky/kaspersky-24/firmware/custom", json=body).status_code == 200
    job = wait_for("kaspersky-24")
    assert job["state"] == "done" and (api / "linux-firmware-custom.tar.gz").exists()
    assert client.delete("/api/kaspersky/kaspersky-24/firmware").json()["removed"] == [
        "linux-firmware-custom.tar.gz"
    ]


def test_api_build_reports_a_bad_choice(api):
    client.post("/api/kaspersky/kaspersky-24/firmware/custom", json={"items": ["nope"]})
    job = wait_for("kaspersky-24")
    assert job["state"] == "error" and "Unknown" in job["error"]


def test_api_full_set(api):
    assert client.post("/api/kaspersky/kaspersky-24/firmware/full").status_code == 200
    assert wait_for("kaspersky-24")["state"] == "done"
    assert (api / fw.FULL_ARCHIVE).exists()


def test_a_machine_report_becomes_a_recommendation(api):
    resp = client.post(
        "/ipxe/krd-report",
        params={
            "mac": "aa:bb:cc:dd:ee:01",
            "manufacturer": "Dell Inc.",
            "product": "Latitude 5530",
        },
        content=DMESG.encode(),
    )
    assert resp.status_code == 204
    got = client.get("/api/kaspersky/firmware-reports").json()
    assert got["reports"][0]["device"] == "Dell Inc. Latitude 5530"
    assert len(got["reports"][0]["items"]) == 2 and len(got["recommended"]) == 2


def test_each_machine_appears_once_and_a_clean_report_is_kept(api):
    params = {"mac": "aa:bb:cc:dd:ee:01", "product": "Latitude 5530"}
    client.post("/ipxe/krd-report", params=params, content=DMESG.encode())
    client.post("/ipxe/krd-report", params=params, content=b"")  # later, nothing missing any more
    other = client.post(
        "/ipxe/krd-report", params={"mac": "aa:bb:cc:dd:ee:02"}, content=DMESG.encode()
    )
    assert other.status_code == 204
    reports = client.get("/api/kaspersky/firmware-reports").json()["reports"]
    assert len(reports) == 2
    mine = next(r for r in reports if r["mac"] == "aa:bb:cc:dd:ee:01")
    assert mine["missing"] == []


def test_reports_are_size_limited_and_can_be_cleared(api):
    big = client.post("/ipxe/krd-report", content=b"x" * (MAX_REPORT_BYTES + 1))
    assert big.status_code == 413
    client.post("/ipxe/krd-report", content=DMESG.encode())
    assert client.delete("/api/kaspersky/firmware-reports").json() == {"cleared": True}
    assert client.get("/api/kaspersky/firmware-reports").json()["reports"] == []


def test_a_report_sent_by_hand_is_recorded_too(api):
    resp = client.post("/api/kaspersky/kaspersky-24/firmware/report", content=DMESG.encode())
    assert resp.status_code == 200 and len(resp.json()["missing"]) == 2


# --- the boot script sends the report -------------------------------------------------


def test_report_url_names_the_machine_and_is_the_only_thing_that_reaches_the_script():
    url = kd.report_url_for(
        "192.168.10.170:9021", {"mac": "aa:bb:cc:dd:ee:01", "product": "Latitude 5530"}
    )
    assert (
        url
        == "http://192.168.10.170:9021/ipxe/krd-report?mac=aa%3Abb%3Acc%3Add%3Aee%3A01&product=Latitude+5530"
    )
    assert f"'{url}'" not in kd.render_hook("off", "") and url in kd.render_hook("off", url)
    for hostile in ("http://x/y?a='; rm -rf /; '", "ftp://x/y?a=1", "http://a b/y?c=1"):
        assert hostile not in kd.render_hook("off", hostile)


def test_hook_endpoint_includes_the_report_address_unless_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "IPXE_ROOT", tmp_path)
    on = client.get("/ipxe/krd-display.sh", params={"mac": "aa:bb:cc:dd:ee:01", "product": "X"})
    assert "/ipxe/krd-report?mac=" in on.text
    client.put(
        "/api/kaspersky/display", json={"default": "auto", "report_firmware": False, "rules": []}
    )
    off = client.get("/ipxe/krd-display.sh")
    assert 'REPORT_URL=""' in off.text


def test_the_installed_report_script_sends_only_the_firmware_lines(tmp_path):
    root = tmp_path / "machine"
    url = kd.report_url_for("192.168.10.170:9021", {"mac": "aa:bb:cc:dd:ee:01"})
    script = root.parent / "hook.sh"
    script.write_text(kd.render_hook("off", url))
    env = {
        "PATH": "/usr/bin:/bin",
        "IPXE_STATION_ROOT": str(root),
        "IPXE_STATION_SYS": str(root / "sys"),
    }
    subprocess.run(["sh", str(script)], env=env, check=True)

    desktop = (root / "etc/xdg/autostart/ipxe-station-report.desktop").read_text()
    assert "Exec=/usr/local/bin/ipxe-station-report" in desktop

    # run the installed script with a made-up dmesg and wget
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    (fakebin / "dmesg").write_text(
        f"#!/bin/sh\ncat <<'EOF'\n{DMESG}\nsome unrelated kernel line\nEOF\n"
    )
    (fakebin / "wget").write_text(
        '#!/bin/sh\nfor a in "$@"; do echo "$a" >> "$SENT/args"; '
        'case $a in --post-file=*) cat "${a#--post-file=}" > "$SENT/body";; esac; done\n'
    )
    for name in ("dmesg", "wget"):
        (fakebin / name).chmod(0o755)
    sent = tmp_path / "sent"
    sent.mkdir()
    subprocess.run(
        [str(root / "usr/local/bin/ipxe-station-report")],
        env={
            "PATH": f"{fakebin}:/usr/bin:/bin",
            "IPXE_STATION_REPORT_DELAY": "0",
            "SENT": str(sent),
        },
        check=True,
    )
    body = (sent / "body").read_text()
    assert "iwlwifi-so-a0-gf-a0-72.ucode" in body and "unrelated" not in body
    assert url in (sent / "args").read_text()

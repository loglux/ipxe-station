"""Kaspersky Rescue Disk upkeep: database updates and the firmware archive the boot hook reads."""

import hashlib
import subprocess
import tarfile
import time

import pytest
from fastapi.testclient import TestClient

import app.backend.krd_maintenance as krd
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


@pytest.fixture
def disk(tmp_path):
    """A minimal extracted KRD folder."""
    folder = tmp_path / "http" / "kaspersky-24"
    (folder / "live" / "KRD").mkdir(parents=True)
    module = folder / krd.BASES_MODULE
    module.write_bytes(b"old databases")
    (folder / krd.TIMESTAMP_FILE).write_text("202509010000\n")
    (folder / krd.VERSION_FILE).write_text("Kaspersky Rescue Disk 24.0.7.0")
    old_sum = hashlib.sha256(b"old databases").hexdigest()
    (folder / krd.CHECKSUM_FILE).write_text(
        f"{'0' * 64}  ./boot/x\n{old_sum}  ./live/KRD/30-bases.srm\n{'1' * 64}  ./live/y\n"
    )
    return folder


# --- parsing -------------------------------------------------------------


def test_parse_folds_wifi_versions_into_one_entry():
    found = {item["name"]: item for item in krd.parse_missing_firmware(DMESG)}
    assert set(found) == {"iwlwifi-so-a0-gf-a0-72.ucode", "intel/ibt-0040-0041.sfi"}
    wifi = found["iwlwifi-so-a0-gf-a0-72.ucode"]
    assert wifi["alternatives"] == ["iwlwifi-so-a0-gf-a0-71.ucode", "iwlwifi-so-a0-gf-a0-39.ucode"]
    assert wifi["companions"] == ["iwlwifi-so-a0-gf-a0.pnvm"]
    assert found["intel/ibt-0040-0041.sfi"]["companions"] == ["intel/ibt-0040-0041.ddc"]


def test_parse_ignores_successful_loads_and_junk():
    assert krd.parse_missing_firmware("firmware: direct-loading firmware regulatory.db") == []
    assert krd.parse_missing_firmware("") == []
    assert krd.parse_missing_firmware("Direct firmware load for ../../etc/passwd failed") == []


def test_presets_cover_the_reported_files():
    names = [m["name"] for m in krd.parse_missing_firmware(DMESG)]
    assert set(krd.presets_covering(names)) == {"intel-ax211", "intel-bluetooth"}


# --- firmware archive ---------------------------------------------------


def fake_release(monkeypatch, files):
    """Pretend kernel.org has exactly these files."""
    monkeypatch.setattr(krd, "_fetch_firmware_file", lambda path, tag: files.get(path))


def test_custom_archive_has_the_layout_the_boot_hook_needs(disk, monkeypatch):
    fake_release(
        monkeypatch,
        {
            "iwlwifi-so-a0-gf-a0-72.ucode": b"ucode",
            "iwlwifi-so-a0-gf-a0.pnvm": b"pnvm",
            "intel/ibt-0040-0041.sfi": b"sfi",
        },
    )
    result = krd.build_custom_firmware(disk, ["intel-ax211"])
    assert result["archive"] == "linux-firmware-custom.tar.gz"
    assert sorted(result["added"]) == ["iwlwifi-so-a0-gf-a0-72.ucode", "iwlwifi-so-a0-gf-a0.pnvm"]

    with tarfile.open(disk / "linux-firmware-custom.tar.gz") as tar:
        names = tar.getnames()
        # the hook derives the folder from the archive name and runs copy-firmware.sh in it
        assert "linux-firmware-custom/copy-firmware.sh" in names
        assert tar.getmember("linux-firmware-custom/copy-firmware.sh").mode & 0o111
        assert "linux-firmware-custom/files/iwlwifi-so-a0-gf-a0-72.ucode" in names


def test_installer_script_copies_files_into_the_target(disk, monkeypatch, tmp_path):
    fake_release(monkeypatch, {"intel/ibt-0040-0041.sfi": b"sfi", "iwlwifi-x-72.ucode": b"u"})
    krd.build_custom_firmware(
        disk, [], [{"name": "intel/ibt-0040-0041.sfi"}, {"name": "iwlwifi-x-72.ucode"}]
    )
    unpacked = tmp_path / "unpacked"
    unpacked.mkdir()
    with tarfile.open(disk / "linux-firmware-custom.tar.gz") as tar:
        tar.extractall(unpacked, filter="data")
    target = tmp_path / "usr-lib-firmware"
    installer = unpacked / "linux-firmware-custom" / "copy-firmware.sh"
    subprocess.run([str(installer), str(target)], check=True)
    assert (target / "intel" / "ibt-0040-0041.sfi").read_bytes() == b"sfi"
    assert (target / "iwlwifi-x-72.ucode").read_bytes() == b"u"


def test_fallback_version_is_used_when_the_newest_is_missing(disk, monkeypatch):
    fake_release(monkeypatch, {"iwlwifi-a-71.ucode": b"71"})
    result = krd.build_custom_firmware(
        disk, [], [{"name": "iwlwifi-a-72.ucode", "alternatives": ["iwlwifi-a-71.ucode"]}]
    )
    assert result["added"] == ["iwlwifi-a-71.ucode"]


def test_missing_files_are_reported_not_fatal(disk, monkeypatch):
    fake_release(monkeypatch, {"iwlwifi-so-a0-gf-a0-72.ucode": b"x"})
    result = krd.build_custom_firmware(disk, ["intel-ax211"])
    assert result["skipped"] == ["iwlwifi-so-a0-gf-a0.pnvm"]


def test_nothing_found_is_an_error_and_leaves_no_archive(disk, monkeypatch):
    fake_release(monkeypatch, {})
    with pytest.raises(krd.KrdError):
        krd.build_custom_firmware(disk, ["intel-ax211"])
    assert krd.firmware_archives(disk) == []
    assert not list(disk.glob("*.tmp"))


@pytest.mark.parametrize("bad", ["../etc/passwd", "/abs/path", "a b.bin", "x/../../y", ""])
def test_bad_names_are_refused(disk, monkeypatch, bad):
    fake_release(monkeypatch, {})
    with pytest.raises(krd.KrdError):
        krd.build_custom_firmware(disk, [], [{"name": bad}])


def test_unknown_preset_is_refused(disk):
    with pytest.raises(krd.KrdError):
        krd.build_custom_firmware(disk, ["nope"])


def test_only_one_firmware_archive_may_remain(disk, monkeypatch):
    """KRD panics at boot when the disk root holds two linux-firmware archives."""
    (disk / "linux-firmware-20230210.tar.gz").write_bytes(b"full")
    fake_release(monkeypatch, {"a.bin": b"a"})
    result = krd.build_custom_firmware(disk, [], [{"name": "a.bin"}])
    assert result["replaced"] == ["linux-firmware-20230210.tar.gz"]
    assert [a.name for a in krd.firmware_archives(disk)] == ["linux-firmware-custom.tar.gz"]
    assert krd.firmware_state(disk)["kind"] == "custom"


# --- databases ----------------------------------------------------------


class FakeResponse:
    def __init__(self, text="", content=b"", status=200):
        self.text, self._content, self.status_code = text, content, status
        self.headers = {"Content-Length": str(len(content))}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise krd.requests.HTTPError(str(self.status_code))

    def iter_content(self, size):
        yield self._content

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_kaspersky(monkeypatch, module=b"fresh databases", stamp="202609261328", digest=None):
    digest = digest or hashlib.sha512(module).hexdigest()

    def get(url, **kwargs):
        if url.endswith("krd.xml"):
            return FakeResponse(
                f'<root><update_info product_version = "24.0.7.0" '
                f'databases_timestamp = "{stamp}" /></root>'
            )
        if url.endswith("hashes.txt"):
            return FakeResponse(f"{digest}  ./42-freshbases.srm\n")
        return FakeResponse(content=module)

    monkeypatch.setattr(krd.requests, "get", get)


def test_status_compares_timestamps(disk, monkeypatch):
    fake_kaspersky(monkeypatch)
    status = krd.bases_status(disk)
    assert status["up_to_date"] is False
    assert status["remote_label"] == "2026-09-26 13:28"
    fake_kaspersky(monkeypatch, stamp="202501010000")
    assert krd.bases_status(disk)["up_to_date"] is True


def test_update_replaces_module_and_bookkeeping(disk, monkeypatch, tmp_path):
    fake_kaspersky(monkeypatch)
    result = krd.update_bases(disk, tmp_path / "backups")
    assert result["updated"] is True
    assert (disk / krd.BASES_MODULE).read_bytes() == b"fresh databases"
    assert (disk / krd.TIMESTAMP_FILE).read_text() == "202609261328\n"
    sums = (disk / krd.CHECKSUM_FILE).read_text().splitlines()
    assert f"{hashlib.sha256(b'fresh databases').hexdigest()}  ./live/KRD/30-bases.srm" in sums
    assert len(sums) == 3  # the other lines are untouched
    backup = next((tmp_path / "backups").iterdir())
    assert (backup / "30-bases.srm").read_bytes() == b"old databases"
    assert (backup / krd.TIMESTAMP_FILE).read_text() == "202509010000\n"
    assert not list((disk / "live" / "KRD").glob("*.download"))


def test_update_with_wrong_checksum_changes_nothing(disk, monkeypatch, tmp_path):
    fake_kaspersky(monkeypatch, digest="f" * 128)
    with pytest.raises(krd.KrdError, match="checksum"):
        krd.update_bases(disk, tmp_path / "backups")
    assert (disk / krd.BASES_MODULE).read_bytes() == b"old databases"
    assert (disk / krd.TIMESTAMP_FILE).read_text() == "202509010000\n"
    assert not list((disk / "live" / "KRD").glob("*.download"))


def test_update_when_current_does_nothing_unless_forced(disk, monkeypatch, tmp_path):
    fake_kaspersky(monkeypatch, stamp="202509010000")
    assert krd.update_bases(disk, tmp_path / "b")["updated"] is False
    assert krd.update_bases(disk, tmp_path / "b", force=True)["updated"] is True


def test_only_the_newest_backups_are_kept(disk, monkeypatch, tmp_path):
    for n in range(krd.KEEP_BACKUPS + 2):
        (disk / krd.TIMESTAMP_FILE).write_text(f"20250{n}010000\n")
        krd._backup_bases(disk, tmp_path / "b")
    assert len(list((tmp_path / "b").iterdir())) == krd.KEEP_BACKUPS


# --- API ----------------------------------------------------------------


@pytest.fixture
def api(disk, tmp_path, monkeypatch):
    monkeypatch.setattr(state, "HTTP_ROOT", disk.parent)
    monkeypatch.setattr(state, "BASE_ROOT", tmp_path)
    monkeypatch.setattr(state, "IPXE_ROOT", tmp_path)
    return disk


def wait_for(name, kind):
    for _ in range(100):
        job = client.get(f"/api/kaspersky/{name}/jobs/{kind}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_api_lists_disks_and_refuses_unknown_ones(api):
    folders = client.get("/api/kaspersky").json()["folders"]
    assert [f["name"] for f in folders] == ["kaspersky-24"]
    assert folders[0]["bases_label"] == "2025-09-01 00:00"
    assert folders[0]["firmware"]["kind"] == "none"
    assert client.get("/api/kaspersky/nope/bases").status_code == 404
    assert client.get("/api/kaspersky/..%2Fx/bases").status_code == 404


def test_api_update_runs_as_a_job(api, monkeypatch):
    fake_kaspersky(monkeypatch)
    assert client.post("/api/kaspersky/kaspersky-24/bases/update").json() == {"started": True}
    job = wait_for("kaspersky-24", "bases")
    assert job["state"] == "done" and job["result"]["updated"] is True


def test_api_update_failure_is_reported(api, monkeypatch):
    fake_kaspersky(monkeypatch, digest="f" * 128)
    client.post("/api/kaspersky/kaspersky-24/bases/update")
    job = wait_for("kaspersky-24", "bases")
    assert job["state"] == "error" and "checksum" in job["error"]


def test_api_scan_and_report(api):
    scan = client.post("/api/kaspersky/kaspersky-24/firmware/scan", json={"text": DMESG}).json()
    assert {m["name"] for m in scan["missing"]} == {
        "iwlwifi-so-a0-gf-a0-72.ucode",
        "intel/ibt-0040-0041.sfi",
    }
    resp = client.post("/api/kaspersky/kaspersky-24/firmware/report", content=DMESG.encode())
    assert resp.status_code == 200 and len(resp.json()["missing"]) == 2
    reports = client.get("/api/kaspersky/kaspersky-24/firmware").json()["reports"]
    assert len(reports) == 1 and reports[0]["missing"][0]["name"]


def test_api_report_size_is_limited(api):
    big = b"x" * (MAX_REPORT_BYTES + 1)
    resp = client.post("/api/kaspersky/kaspersky-24/firmware/report", content=big)
    assert resp.status_code == 413


def test_api_build_and_remove_firmware(api, monkeypatch):
    fake_release(monkeypatch, {"intel/ibt-0040-0041.sfi": b"sfi"})
    body = {"presets": [], "files": [{"name": "intel/ibt-0040-0041.sfi"}]}
    assert client.post("/api/kaspersky/kaspersky-24/firmware/custom", json=body).status_code == 200
    assert wait_for("kaspersky-24", "firmware")["state"] == "done"
    assert (api / "linux-firmware-custom.tar.gz").exists()
    removed = client.delete("/api/kaspersky/kaspersky-24/firmware").json()["removed"]
    assert removed == ["linux-firmware-custom.tar.gz"]


def test_full_download_is_verified(disk, monkeypatch):
    payload = b"tarball"
    good = hashlib.sha256(payload).hexdigest()

    def get(url, **kwargs):
        if url.endswith("sha256sums.asc"):
            return FakeResponse(f"{good}  {krd.FULL_ARCHIVE}\n")
        return FakeResponse(content=payload)

    monkeypatch.setattr(krd.requests, "get", get)
    monkeypatch.setattr(krd.shutil, "disk_usage", lambda p: type("U", (), {"free": 10**10})())
    assert krd.install_full_firmware(disk)["archive"] == krd.FULL_ARCHIVE

    monkeypatch.setattr(
        krd.requests,
        "get",
        lambda url, **kw: (
            FakeResponse(f"{'0' * 64}  {krd.FULL_ARCHIVE}\n")
            if url.endswith("asc")
            else FakeResponse(content=payload)
        ),
    )
    (disk / krd.FULL_ARCHIVE).unlink()
    with pytest.raises(krd.KrdError, match="checksum"):
        krd.install_full_firmware(disk)
    assert krd.firmware_archives(disk) == []


def test_requests_to_kernel_org_carry_a_user_agent(monkeypatch):
    """kernel.org refuses the default python-requests agent with 403."""
    seen = []

    def get(url, **kwargs):
        seen.append(kwargs.get("headers"))
        return FakeResponse(content=b"x")

    monkeypatch.setattr(krd.requests, "get", get)
    assert krd._fetch_firmware_file("a.bin", krd.FIRMWARE_TAG) == b"x"
    assert seen == [krd.HEADERS] and krd.HEADERS["User-Agent"]

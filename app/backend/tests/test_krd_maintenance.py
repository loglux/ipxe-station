"""Kaspersky Rescue Disk upkeep: database updates and the firmware archive the boot hook reads."""

import hashlib
import time

import pytest
from fastapi.testclient import TestClient

import app.backend.krd_maintenance as krd
from app.main import app
from app.routes import state

client = TestClient(app)


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

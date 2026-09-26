"""Scheduled check of the Kaspersky databases: when it is due, what it does, and the API."""

import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.backend.krd_maintenance as krd
import app.backend.krd_schedule as ks
from app.backend.krd_schedule import Schedule
from app.main import app
from app.routes import state

client = TestClient(app)

# 2026-09-26 is a Saturday
SAT_15 = datetime(2026, 9, 26, 15, 0)


def at(day, hour, minute=0):
    return datetime(2026, 9, day, hour, minute)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(ks, "_last_boot", 0.0)
    monkeypatch.setattr(ks, "POLL_SECONDS", 0.01)
    krd._jobs.clear()


# --- when it is due --------------------------------------------------------------------


def test_daily_runs_at_the_set_time_each_day():
    s = Schedule(enabled=True, time="03:00")
    assert ks.most_recent_due(s, SAT_15) == at(26, 3)
    assert ks.most_recent_due(s, at(26, 2, 59)) == at(25, 3)
    assert ks.most_recent_due(s, at(26, 3, 0)) == at(26, 3)
    assert ks.next_due(s, SAT_15) == at(27, 3)
    assert ks.next_due(s, at(26, 2, 0)) == at(26, 3)


def test_weekly_runs_on_the_chosen_weekday():
    monday = Schedule(enabled=True, frequency="weekly", weekday=0, time="03:00")
    assert ks.most_recent_due(monday, SAT_15) == at(21, 3)  # Monday the 21st
    assert ks.next_due(monday, SAT_15) == at(28, 3)
    same_day = Schedule(enabled=True, frequency="weekly", weekday=5, time="03:00")  # Saturday
    assert ks.most_recent_due(same_day, SAT_15) == at(26, 3)
    assert ks.most_recent_due(same_day, at(26, 2)) == at(19, 3)


def test_due_only_when_enabled_and_a_moment_has_passed_since_the_last_run():
    s = Schedule(enabled=True, time="03:00")
    assert not ks.is_due(Schedule(enabled=False), SAT_15, 0)
    assert not ks.is_due(s, SAT_15, None)
    assert ks.is_due(s, SAT_15, at(25, 12).timestamp())
    assert not ks.is_due(s, SAT_15, at(26, 3, 1).timestamp())


@pytest.mark.parametrize("bad", ["3:00", "24:00", "03:60", "", "noon", "03-00"])
def test_a_bad_time_is_refused(bad):
    with pytest.raises(ValueError):
        Schedule(time=bad)


# --- stored state ----------------------------------------------------------------------


def test_turning_it_on_counts_from_now_not_from_todays_missed_slot(tmp_path):
    path = tmp_path / "s.json"
    ks.save_schedule(path, Schedule(enabled=True, time="03:00"), SAT_15)
    stored = ks.load_state(path)
    assert not ks.is_due(stored["schedule"], SAT_15 + timedelta(hours=1), stored["last_run"])
    assert ks.is_due(stored["schedule"], at(27, 3, 1), stored["last_run"])


def test_saving_the_same_schedule_again_does_not_postpone_the_run(tmp_path):
    path = tmp_path / "s.json"
    s = Schedule(enabled=True, time="03:00")
    ks.save_schedule(path, s, at(25, 12))
    first = ks.load_state(path)["last_run"]
    ks.save_schedule(path, s, at(26, 9))
    assert ks.load_state(path)["last_run"] == first
    ks.save_schedule(path, Schedule(enabled=True, time="04:00"), at(26, 9))
    assert ks.load_state(path)["last_run"] == at(26, 9).timestamp()


def test_a_missing_or_broken_file_means_the_defaults(tmp_path):
    assert ks.load_state(tmp_path / "none.json")["schedule"] == Schedule()
    (tmp_path / "bad.json").write_text("{not json")
    assert ks.load_state(tmp_path / "bad.json")["schedule"].enabled is False


# --- the job -----------------------------------------------------------------------------


def status(local="202603061200", remote="202609261328", error=""):
    fmt = krd.format_timestamp
    return {
        "local": local,
        "local_label": fmt(local),
        "remote": remote,
        "remote_label": fmt(remote),
        "up_to_date": bool(local) and local >= remote and not error,
        "error": error,
    }


@pytest.fixture
def updates():
    return []


@pytest.fixture
def disk(tmp_path, monkeypatch, updates):
    folder = tmp_path / "http" / "kaspersky-24"
    (folder / "live" / "KRD").mkdir(parents=True)
    monkeypatch.setattr(krd, "bases_status", lambda f: status())
    monkeypatch.setattr(
        krd,
        "update_bases",
        lambda f, backups, progress=None, force=False: updates.append(f.name)
        or {"updated": True, "message": "Databases updated to 2026-09-26 13:28."},
    )
    return folder


def run(schedule, disk, tmp_path, now=None):
    return ks.run_job(schedule, [disk], tmp_path / "backups", now)


def test_check_only_reports_what_is_published_and_changes_nothing(disk, tmp_path, updates):
    result = run(Schedule(enabled=True, action="check"), disk, tmp_path)
    entry = result["folders"][0]
    assert entry["state"] == "available" and "2026-09-26 13:28" in entry["message"]
    assert updates == []


def test_a_current_disk_is_reported_as_current(disk, tmp_path, monkeypatch, updates):
    monkeypatch.setattr(krd, "bases_status", lambda f: status(local="202609261328"))
    result = run(Schedule(enabled=True, action="update"), disk, tmp_path)
    assert result["folders"][0]["state"] == "current" and updates == []


def test_a_server_that_cannot_be_reached_is_an_error_not_a_crash(
    disk, tmp_path, monkeypatch, updates
):
    monkeypatch.setattr(krd, "bases_status", lambda f: status(error="Could not reach Kaspersky"))
    result = run(Schedule(enabled=True, action="update"), disk, tmp_path)
    assert result["folders"][0]["state"] == "error" and updates == []


def test_update_action_updates_a_disk_that_is_behind(disk, tmp_path, updates):
    result = run(Schedule(enabled=True, action="update"), disk, tmp_path)
    assert result["folders"][0]["state"] == "updated" and updates == ["kaspersky-24"]
    assert "updated to" in result["folders"][0]["message"]


def test_a_failed_update_is_reported(disk, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise krd.KrdError("checksum mismatch")

    monkeypatch.setattr(krd, "update_bases", boom)
    result = run(Schedule(enabled=True, action="update"), disk, tmp_path)
    assert result["folders"][0]["state"] == "error"
    assert "checksum mismatch" in result["folders"][0]["message"]


def test_an_update_waits_while_a_machine_has_just_started_kaspersky(disk, tmp_path, updates):
    now = time.time()
    ks.note_boot(now - 3600)  # an hour ago
    result = run(Schedule(enabled=True, action="update", quiet_hours=4), disk, tmp_path, now)
    entry = result["folders"][0]
    assert entry["state"] == "postponed" and "within the last 4 h" in entry["message"]
    assert updates == []


def test_an_old_boot_does_not_hold_the_update_back(disk, tmp_path):
    now = time.time()
    ks.note_boot(now - 6 * 3600)
    result = run(Schedule(enabled=True, action="update", quiet_hours=4), disk, tmp_path, now)
    assert result["folders"][0]["state"] == "updated"


def test_zero_quiet_hours_switches_the_wait_off(disk, tmp_path):
    ks.note_boot()
    result = run(Schedule(enabled=True, action="update", quiet_hours=0), disk, tmp_path)
    assert result["folders"][0]["state"] == "updated"


def test_check_only_never_waits(disk, tmp_path):
    ks.note_boot()
    assert (
        run(Schedule(enabled=True, action="check"), disk, tmp_path)["folders"][0]["state"]
        == "available"
    )


def test_an_update_already_running_is_left_alone(disk, tmp_path, updates):
    krd._jobs["kaspersky-24:bases"] = {"state": "running"}
    result = run(Schedule(enabled=True, action="update"), disk, tmp_path)
    assert result["folders"][0]["state"] == "postponed" and updates == []


def test_booted_within():
    assert not ks.booted_within(4)
    ks.note_boot(1000.0)
    assert ks.booted_within(4, now=1000.0 + 3 * 3600)
    assert not ks.booted_within(4, now=1000.0 + 5 * 3600)
    assert not ks.booted_within(0, now=1000.0)


# --- the tick ----------------------------------------------------------------------------


def test_tick_runs_once_when_due_and_records_the_result(disk, tmp_path):
    path = tmp_path / "s.json"
    ks.save_schedule(path, Schedule(enabled=True, time="03:00"), at(25, 12))
    logged = []
    result = ks.tick(path, [disk], tmp_path / "b", at(26, 3, 1), log=logged.append)
    assert result["folders"][0]["state"] == "available" and logged
    assert ks.load_state(path)["last"]["folders"][0]["state"] == "available"
    assert ks.tick(path, [disk], tmp_path / "b", at(26, 3, 2)) is None  # not again the same day
    assert ks.tick(path, [disk], tmp_path / "b", at(27, 3, 1)) is not None  # tomorrow again


def test_tick_does_nothing_before_the_time_or_when_switched_off(disk, tmp_path):
    path = tmp_path / "s.json"
    ks.save_schedule(path, Schedule(enabled=True, time="03:00"), at(25, 12))
    assert ks.tick(path, [disk], tmp_path / "b", at(26, 2, 59)) is None
    ks.save_schedule(path, Schedule(enabled=False, time="03:00"), at(25, 12))
    assert ks.tick(path, [disk], tmp_path / "b", at(27, 9)) is None


def test_a_run_missed_because_the_server_was_down_is_made_up_once(disk, tmp_path):
    path = tmp_path / "s.json"
    ks.save_schedule(path, Schedule(enabled=True, time="03:00"), at(20, 12))
    assert ks.tick(path, [disk], tmp_path / "b", at(26, 15)) is not None
    assert ks.tick(path, [disk], tmp_path / "b", at(26, 15, 1)) is None


def test_a_crashing_job_is_not_retried_every_minute(disk, tmp_path, monkeypatch):
    path = tmp_path / "s.json"
    ks.save_schedule(path, Schedule(enabled=True, time="03:00"), at(25, 12))
    monkeypatch.setattr(krd, "bases_status", lambda f: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        ks.tick(path, [disk], tmp_path / "b", at(26, 3, 1))
    assert ks.tick(path, [disk], tmp_path / "b", at(26, 3, 2)) is None


# --- boot notes ---------------------------------------------------------------------------


def request_for():
    return SimpleNamespace(client=SimpleNamespace(host="10.0.0.5"))


def test_a_kaspersky_kernel_request_counts_as_a_boot_and_others_do_not():
    state._record_http_boot_flow(request_for(), "/http/ubuntu-24.04/casper/vmlinuz", 200)
    assert not ks.booted_within(1)
    state._record_http_boot_flow(request_for(), "/http/kaspersky-24/live/vmlinuz", 404)
    assert not ks.booted_within(1)
    state._record_http_boot_flow(request_for(), "/http/kaspersky-24/live/vmlinuz", 200)
    assert ks.booted_within(1)


def test_the_boot_script_request_counts_as_a_boot(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "IPXE_ROOT", tmp_path)
    client.get("/ipxe/krd-display.sh", params={"product": "X"})
    assert ks.booted_within(1)


# --- API ---------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path, monkeypatch, disk):
    monkeypatch.setattr(state, "HTTP_ROOT", disk.parent)
    monkeypatch.setattr(state, "BASE_ROOT", tmp_path)
    monkeypatch.setattr(state, "IPXE_ROOT", tmp_path)
    (disk / "live" / "KRD" / "30-bases.srm").write_bytes(b"x")
    return disk


def test_api_defaults_to_off_and_shows_the_servers_clock(api):
    got = client.get("/api/kaspersky/schedule").json()
    assert got["schedule"]["enabled"] is False and got["next_run"] == "" and got["last"] is None
    assert len(got["server_time"]) == 5 and got["timezone"]


def test_api_saves_a_schedule_and_says_when_it_runs_next(api):
    body = {
        "enabled": True,
        "frequency": "daily",
        "time": "03:00",
        "weekday": 0,
        "action": "check",
        "quiet_hours": 4,
    }
    got = client.put("/api/kaspersky/schedule", json=body).json()
    assert got["schedule"]["time"] == "03:00" and got["next_run"].endswith("03:00")
    assert client.get("/api/kaspersky/schedule").json()["schedule"]["enabled"] is True


@pytest.mark.parametrize(
    "bad",
    [
        {"time": "25:00"},
        {"frequency": "hourly"},
        {"action": "explode"},
        {"weekday": 9},
        {"quiet_hours": 99},
        {"nope": 1},
    ],
)
def test_api_refuses_a_bad_schedule(api, bad):
    assert client.put("/api/kaspersky/schedule", json=bad).status_code == 422


def test_api_run_now_checks_and_the_result_is_kept(api):
    assert client.post("/api/kaspersky/schedule/run").json() == {"started": True}
    for _ in range(100):
        job = client.get("/api/kaspersky/schedule/job").json()
        if job["state"] != "running":
            break
        time.sleep(0.05)
    assert job["state"] == "done" and job["result"]["folders"][0]["state"] == "available"
    assert (
        client.get("/api/kaspersky/schedule").json()["last"]["folders"][0]["state"] == "available"
    )

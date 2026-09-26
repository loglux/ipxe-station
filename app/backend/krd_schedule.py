"""A scheduled check (or update) of the Kaspersky Rescue Disk antivirus databases.

The schedule is set from the admin page. A background thread wakes every minute and runs the job
when its time has come. Two actions exist: ``check`` only records whether newer databases are
published; ``update`` also replaces them, but never while a machine has probably just started
Kaspersky from the network, because a running system reads that file.
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from . import krd_maintenance as krd

_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
POLL_SECONDS = 2
UPDATE_TIMEOUT_SECONDS = 30 * 60


class Schedule(BaseModel):
    enabled: bool = False
    frequency: Literal["daily", "weekly"] = "daily"
    time: str = "03:00"  # HH:MM on the server's clock
    weekday: int = Field(0, ge=0, le=6)  # 0 = Monday; used when weekly
    action: Literal["check", "update"] = "check"
    # do not update while a machine started Kaspersky within this many hours
    quiet_hours: int = Field(4, ge=0, le=48)

    model_config = {"extra": "forbid"}

    @field_validator("time")
    @classmethod
    def _time_ok(cls, value: str) -> str:
        if not _TIME.match(value):
            raise ValueError("time must be HH:MM, 00:00 to 23:59")
        return value


# ---------------------------------------------------------------------------
# When a run is due
# ---------------------------------------------------------------------------


def _at(day: datetime, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def most_recent_due(schedule: Schedule, now: datetime) -> datetime:
    """The latest moment at or before ``now`` when the schedule says to run."""
    moment = _at(now, schedule.time)
    if moment > now:
        moment -= timedelta(days=1)
    if schedule.frequency == "weekly":
        moment -= timedelta(days=(moment.weekday() - schedule.weekday) % 7)
    return moment


def next_due(schedule: Schedule, now: datetime) -> datetime:
    """The first moment after ``now`` when the schedule says to run."""
    moment = most_recent_due(schedule, now)
    step = timedelta(days=7 if schedule.frequency == "weekly" else 1)
    while moment <= now:
        moment += step
    return moment


def is_due(schedule: Schedule, now: datetime, last_run: Optional[float]) -> bool:
    if not schedule.enabled:
        return False
    if last_run is None:
        return False
    return most_recent_due(schedule, now).timestamp() > last_run


# ---------------------------------------------------------------------------
# Stored state
# ---------------------------------------------------------------------------


def load_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        schedule = Schedule(**data.get("schedule", {}))
    except (TypeError, ValueError):
        schedule = Schedule()
    return {"schedule": schedule, "last_run": data.get("last_run"), "last": data.get("last")}


def _write_state(path: Path, state: dict) -> None:
    payload = {
        "schedule": state["schedule"].model_dump(),
        "last_run": state["last_run"],
        "last": state["last"],
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)


def save_schedule(path: Path, schedule: Schedule, now: datetime) -> dict:
    """Store a new schedule. Turning it on, or changing it, starts counting from now, so saving at
    15:00 a run set for 03:00 waits for tomorrow instead of firing at once."""
    state = load_state(path)
    if schedule != state["schedule"] or state["last_run"] is None:
        state["last_run"] = now.timestamp()
    state["schedule"] = schedule
    _write_state(path, state)
    return state


# ---------------------------------------------------------------------------
# Has a machine just started Kaspersky?
# ---------------------------------------------------------------------------

_last_boot = 0.0
_boot_lock = threading.Lock()


def note_boot(when: Optional[float] = None) -> None:
    """Called when a machine asks for Kaspersky's kernel (or its boot script)."""
    global _last_boot
    with _boot_lock:
        _last_boot = when if when is not None else time.time()


def booted_within(hours: int, now: Optional[float] = None) -> bool:
    if hours <= 0:
        return False
    with _boot_lock:
        last = _last_boot
    return last > 0 and (now if now is not None else time.time()) - last < hours * 3600


# ---------------------------------------------------------------------------
# Running it
# ---------------------------------------------------------------------------


def _describe(status: dict) -> str:
    if status["error"]:
        return status["error"]
    if status["up_to_date"]:
        return f"Up to date ({status['local_label']})."
    on_disk = status["local_label"] or "unknown"
    return f"Newer databases are published: {status['remote_label']} (on the disk: {on_disk})."


def _update_folder(folder: Path, backup_root: Path) -> dict:
    """Run the update through the shared job registry (so the page shows it) and wait for it."""
    key = f"{folder.name}:bases"
    if krd.job_status(key).get("state") == "running":
        return {"state": "postponed", "message": "An update is already running."}

    def work(progress):
        return krd.update_bases(folder, backup_root, progress)

    krd.start_job(key, work)
    deadline = time.time() + UPDATE_TIMEOUT_SECONDS
    while time.time() < deadline:
        job = krd.job_status(key)
        if job.get("state") == "done":
            return {"state": "updated", "message": job["result"]["message"]}
        if job.get("state") == "error":
            return {"state": "error", "message": job["error"]}
        time.sleep(POLL_SECONDS)
    return {"state": "error", "message": "The update did not finish in time."}


def run_job(
    schedule: Schedule,
    folders: List[Path],
    backup_root: Path,
    now: Optional[float] = None,
    log: Callable[[str], None] = lambda message: None,
) -> dict:
    """Check every disk and, if asked, update the ones that are behind."""
    results: List[Dict] = []
    for folder in folders:
        status = krd.bases_status(folder)
        entry = {
            "name": folder.name,
            "local": status["local"],
            "remote": status["remote"],
            "message": _describe(status),
        }
        if status["error"]:
            entry["state"] = "error"
        elif status["up_to_date"]:
            entry["state"] = "current"
        elif schedule.action == "check":
            entry["state"] = "available"
        elif booted_within(schedule.quiet_hours, now):
            entry["state"] = "postponed"
            hours = schedule.quiet_hours
            entry[
                "message"
            ] += f" Not updated: a machine started Kaspersky within the last {hours} h."
        else:
            entry.update(_update_folder(folder, backup_root))
        log(f"Kaspersky databases ({folder.name}): {entry['state']}: {entry['message']}")
        results.append(entry)
    stamp = datetime.fromtimestamp(now if now is not None else time.time())
    return {"at": stamp.strftime("%Y-%m-%d %H:%M"), "action": schedule.action, "folders": results}


def tick(
    state_path: Path,
    folders: List[Path],
    backup_root: Path,
    now: Optional[datetime] = None,
    log: Callable[[str], None] = lambda message: None,
) -> Optional[dict]:
    """Run the job if it is due. Returns the result, or None when nothing was due."""
    now = now or datetime.now()
    state = load_state(state_path)
    if not is_due(state["schedule"], now, state["last_run"]):
        return None
    # Mark the run first: a failure must not make the job repeat every minute.
    state["last_run"] = now.timestamp()
    _write_state(state_path, state)
    result = run_job(state["schedule"], folders, backup_root, now.timestamp(), log)
    state["last"] = result
    _write_state(state_path, state)
    return result


def run_now(
    state_path: Path,
    folders: List[Path],
    backup_root: Path,
    log: Callable[[str], None] = lambda message: None,
) -> dict:
    """Run the job right away (the page's "Run now"); it does not move the schedule."""
    state = load_state(state_path)
    result = run_job(state["schedule"], folders, backup_root, None, log)
    state["last"] = result
    _write_state(state_path, state)
    return result

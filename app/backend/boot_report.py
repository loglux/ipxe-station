"""Boot reports from live systems: what a machine says about itself after it has started.

A live system that was booted from this server fetches a small script (see boot_report_hook.sh)
that, once the desktop is up, collects a few sections of plain text and posts them back. This module
turns that text into a summary (memory, problems, devices without a driver, battery health, missing
firmware) and keeps the last report of each machine and system.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode

from .krd_firmware import parse_missing_firmware

HOOK_TEMPLATE = Path(__file__).with_name("boot_report_hook.sh")
COLLECTOR = Path(__file__).with_name("boot_report_collector.sh")
DEBUG_TEMPLATE = Path(__file__).with_name("boot_debug.sh")
DEBUG_PATH = "/ipxe/boot-report-debug"
MAX_DEBUG = 10
HOOK_PATH = "/ipxe/live-report.sh"
REPORT_PATH = "/ipxe/boot-report"
HOOK_QUERY_FIELDS = ("mac", "manufacturer", "product")
DEFAULT_DELAY_SECONDS = 45
LAYER_FILE = "casper/zz-ipxe-station.squashfs"
LAYER_UNIT = "ipxe-station-report.service"
MEDIUM_HOOK_FILE = "live/config-hooks/ipxe-station-report.sh"
# live-config runs a local file named by file://. Its own "medium" mode looks in
# /lib/live/mount/medium, where Debian 13 no longer mounts the medium (it is /run/live/medium), so
# the file is named directly, under both paths; the one that does not exist is skipped.
MEDIUM_HOOK_ARG = (
    "live-config.hooks="
    f"file:///run/live/medium/{MEDIUM_HOOK_FILE}|file:///lib/live/mount/medium/{MEDIUM_HOOK_FILE}"
)

MAX_BODY_BYTES = 300 * 1024
SECTION_LIMIT = 16 * 1024
TOTAL_LIMIT = 120 * 1024
MAX_REPORTS = 200
# Raised whenever the summary learns something new, so stored reports are summarised again.
SUMMARY_VERSION = 2

SECTIONS = (
    "system",
    "memory",
    "cpu",
    "dmi",
    "disks",
    "pci",
    "usb",
    "network",
    "display",
    "power",
    "kernel-messages",
    "failed-units",
    "journal-errors",
)

# Kernel lines that point at failing memory or a failing disk.
_MEMORY_ERROR = re.compile(
    r"MEMORY ERROR|EDAC .*\b(error|CE|UE)\b|machine check|mce: .*(error|corrected)"
    r"|uncorrect|correctable",
    re.I,
)
_DISK_ERROR = re.compile(
    r"I/O error|blk_update_request|Buffer I/O|ata\d+.*(failed|error|exception)"
    r"|nvme\d+.*(timeout|error|reset)|critical medium|medium error",
    re.I,
)
# Missing firmware that is not a problem: debug traces the Wi-Fi driver asks for.
_HARMLESS_FIRMWARE = ("iwl-debug",)

_MARK = re.compile(r"^##### ([a-z-]+)\s*$")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SAFE_URL = re.compile(r"^http://[A-Za-z0-9.\-:]+/[A-Za-z0-9/_.\-]*(\?[A-Za-z0-9=&%+._\-]*)?$")
_FOLDER = re.compile(r"^[A-Za-z0-9._-]+$")

# PCI classes where a missing driver means something does not work.
_NEEDS_DRIVER = (
    "Network controller",
    "Ethernet controller",
    "VGA compatible controller",
    "3D controller",
    "Display controller",
    "Audio device",
    "Multimedia audio controller",
    "Non-Volatile memory controller",
    "SATA controller",
    "RAID bus controller",
    "Bluetooth",
    "Signal processing controller",
)
_SLOT = re.compile(r"^([0-9a-f]{2,4}:)?[0-9a-f]{2}:[0-9a-f]{2}\.\d\s+([^:]+):\s*(.*)$")


# ---------------------------------------------------------------------------
# The script the machine runs
# ---------------------------------------------------------------------------


def render_hook(report_url: str, delay: int = DEFAULT_DELAY_SECONDS) -> str:
    if report_url and not _SAFE_URL.match(report_url):
        report_url = ""  # nothing but a plain http URL ever goes into a script
    delay = max(0, min(int(delay), 600))
    return (
        HOOK_TEMPLATE.read_text()
        .replace("__COLLECTOR__", COLLECTOR.read_text().rstrip("\n"))
        .replace("__REPORT_URL__", report_url)
        .replace("__DELAY__", str(delay))
    )


def report_url_for(host: str, device: dict) -> str:
    """Where the machine sends its report, naming itself by MAC and model."""
    query = urlencode({k: device[k] for k in HOOK_QUERY_FIELDS if device.get(k)})
    return f"http://{host}{REPORT_PATH}?{query}"


def hook_argument() -> str:
    """The kernel argument that makes a live-config system fetch and run the script."""
    query = "&".join(
        [
            "mac=${net0/mac}",
            "manufacturer=${manufacturer:uristring}",
            "product=${product:uristring}",
        ]
    )
    return f"live-config.hooks=http://${{server_ip}}:${{port}}{HOOK_PATH}?{query}"


def is_hook_token(token: str) -> bool:
    """Any of our arguments, including the older "medium" form, so they get replaced."""
    if token.startswith(("ipxe.report=", "ipxe.mac=")):
        return True
    if not token.startswith("live-config.hooks="):
        return False
    return token == "live-config.hooks=medium" or HOOK_PATH in token or MEDIUM_HOOK_FILE in token


def layer_arguments() -> List[str]:
    """What turns the report on for an Ubuntu (casper) entry that has our layer on its medium."""
    return ["ipxe.report=http://${server_ip}:${port}" + REPORT_PATH, "ipxe.mac=${net0/mac}"]


# ---------------------------------------------------------------------------
# Two ways to get the script onto the machine
# ---------------------------------------------------------------------------
#
# By URL: live-config downloads it with wget, so the image needs wget (Debian 13's live image has
# curl only, and then live-config silently fetches nothing).
# From the medium: over NFS the extracted disk is the medium, and live-config runs our file from
# live/config-hooks/ of it by its file:// path. No download, no wget.


def image_folder(kernel: str) -> Optional[str]:
    """The disk folder of an entry whose kernel is in ``<folder>/live/`` or ``<folder>/casper/``."""
    parts = (kernel or "").split("/")
    ok = len(parts) >= 3 and parts[1] in ("live", "casper") and _FOLDER.match(parts[0])
    return parts[0] if ok else None


def image_has_wget(http_root: Path, folder: str) -> Optional[bool]:
    """Whether the live image has wget, from its package list; None when there is no list."""
    try:
        text = (http_root / folder / "live" / "filesystem.packages").read_text()
    except OSError:
        return None
    return any(line.split("\t", 1)[0].strip() == "wget" for line in text.splitlines())


def entry_mode(tokens: List[str], kernel: str, http_root: Path) -> dict:
    """How an entry could send a report, and why not when it cannot."""
    folder = image_folder(kernel)
    if "boot=casper" in tokens:
        # Ubuntu: casper stacks every *.squashfs of the medium's casper/ folder when no layerfs-path
        # is given, so over NFS a small layer of ours joins the system.
        if not any(t.startswith("netboot=nfs") for t in tokens):
            return {
                "mode": "layer",
                "supported": False,
                "reason": "Only an NFS entry can take the report layer (the disk is its medium).",
            }
        if any(t.startswith("layerfs-path=") for t in tokens):
            return {
                "mode": "layer",
                "supported": False,
                "reason": "This entry names its layers (layerfs-path); an added one is not used.",
            }
        if folder:
            return {"mode": "layer", "supported": True, "reason": ""}
        return {
            "mode": "layer",
            "supported": False,
            "reason": "Its kernel is not in a casper/ folder.",
        }
    if any(t.startswith("netboot=nfs") for t in tokens):
        if folder:
            return {"mode": "medium", "supported": True, "reason": ""}
        return {
            "mode": "medium",
            "supported": False,
            "reason": "Its kernel is not in a live/ folder.",
        }
    if folder and image_has_wget(http_root, folder) is False:
        return {
            "mode": "url",
            "supported": False,
            "reason": (
                "This image has no wget, which live-config needs to fetch the script. "
                "Add an NFS entry for it instead."
            ),
        }
    return {"mode": "url", "supported": True, "reason": ""}


def hook_file(http_root: Path, folder: str) -> Path:
    return http_root / folder / MEDIUM_HOOK_FILE


def install_medium_hook(http_root: Path, folder: str, report_base_url: str) -> Path:
    """Put the script in the disk's live/config-hooks/, where live-config finds it over NFS."""
    if not _FOLDER.match(folder):
        raise ValueError("invalid folder")
    target = hook_file(http_root, folder)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(render_hook(report_base_url))
    os.chmod(tmp, 0o755)
    os.replace(tmp, target)
    return target


def remove_medium_hook(http_root: Path, folder: str) -> bool:
    target = hook_file(http_root, folder)
    if not target.exists():
        return False
    target.unlink()
    try:
        target.parent.rmdir()  # the folder goes with it when it was only ours
    except OSError:
        pass
    return True


# ---------------------------------------------------------------------------
# Reading a report
# ---------------------------------------------------------------------------


def clean(text: str) -> str:
    return _CONTROL.sub("", text.replace("\r", ""))


def parse_sections(body: str) -> Dict[str, str]:
    """Split the posted text into its known sections, cleaned and size-limited."""
    sections: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for raw in clean(body).split("\n"):
        mark = _MARK.match(raw)
        if mark:
            name = mark.group(1)
            current = name if name in SECTIONS else None
            if current:
                sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(raw)
    result: Dict[str, str] = {}
    total = 0
    for name in SECTIONS:
        if name not in sections:
            continue
        text = "\n".join(sections[name]).strip("\n")[:SECTION_LIMIT]
        total += len(text)
        if total > TOTAL_LIMIT:
            break
        result[name] = text
    return result


def key_values(text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip():
            values[key.strip()] = value.strip()
    return values


def _kb(sections: Dict[str, str], key: str) -> int:
    match = re.search(rf"^{key}:\s+(\d+)\s*kB", sections.get("memory", ""), re.M)
    return int(match.group(1)) if match else 0


def devices_without_driver(pci_text: str) -> List[str]:
    """PCI devices of classes that need a driver but show none in use (from ``lspci -nnk``)."""
    found: List[str] = []
    block: Optional[str] = None
    has_driver = False

    def close() -> None:
        if block and not has_driver:
            found.append(block)

    for line in pci_text.splitlines():
        match = _SLOT.match(line)
        if match:
            close()
            block, has_driver = None, False
            if any(match.group(2).startswith(cls) for cls in _NEEDS_DRIVER):
                block = f"{match.group(2)}: {match.group(3)}"[:160]
        elif block and "Kernel driver in use" in line:
            has_driver = True
    close()
    return found


def batteries(power_text: str) -> List[dict]:
    out: List[dict] = []
    for line in power_text.splitlines():
        parts = line.split()
        if not parts:
            continue
        fields = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
        if fields.get("type") != "Battery":
            continue
        full = int(fields.get("energy_full") or fields.get("charge_full") or 0)
        design = int(fields.get("energy_full_design") or fields.get("charge_full_design") or 0)
        entry = {
            "name": parts[0],
            "status": fields.get("status", ""),
            "cycles": fields.get("cycle_count", ""),
        }
        if fields.get("capacity", "").isdigit():
            entry["charge_pct"] = int(fields["capacity"])
        if full and design:
            entry["health_pct"] = round(100 * full / design)
        out.append(entry)
    return out


def _lines(text: str) -> List[str]:
    return [line for line in text.splitlines() if line.strip()]


def summarize(sections: Dict[str, str]) -> dict:
    system = key_values(sections.get("system", ""))
    dmi = key_values(sections.get("dmi", ""))
    cpu = sections.get("cpu", "")
    cpu_line = next((line for line in cpu.splitlines() if "model name" in line), "")
    threads = key_values(cpu).get("threads", "")
    kernel_text = sections.get("kernel-messages", "")
    missing = parse_missing_firmware(kernel_text)
    pci = sections.get("pci", "")
    usb = sections.get("usb", "")
    return {
        "os": system.get("os", ""),
        "kernel": system.get("kernel", ""),
        "arch": system.get("arch", ""),
        "boot": system.get("boot", ""),
        "uptime_s": int(system["uptime_s"]) if system.get("uptime_s", "").isdigit() else None,
        "ram_mb": _kb(sections, "MemTotal") // 1024,
        "cpu": cpu_line.split(":", 1)[-1].strip(),
        "threads": int(threads) if threads.isdigit() else None,
        "model": " ".join(p for p in (dmi.get("sys_vendor"), dmi.get("product_name")) if p),
        "kernel_problem_lines": len(_lines(kernel_text)),
        "failed_units": [line.split()[0] for line in _lines(sections.get("failed-units", ""))],
        "missing_firmware": sorted(
            {m["name"] for m in missing if not m["name"].startswith(_HARMLESS_FIRMWARE)}
        ),
        "memory_errors": len([ln for ln in _lines(kernel_text) if _MEMORY_ERROR.search(ln)]),
        "disk_errors": len([ln for ln in _lines(kernel_text) if _DISK_ERROR.search(ln)]),
        "no_driver": devices_without_driver(pci),
        "batteries": batteries(sections.get("power", "")),
        "has_wifi": bool(re.search(r"Network controller|Wireless|802\.11|Wi-?Fi", pci + usb, re.I)),
        "has_bluetooth": bool(re.search(r"Bluetooth", pci + usb, re.I)),
        "journal_errors": len(_lines(sections.get("journal-errors", ""))),
    }


# ---------------------------------------------------------------------------
# Keeping reports
# ---------------------------------------------------------------------------


def _load(path: Path) -> List[dict]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _save(path: Path, reports: List[dict]) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(reports[-MAX_REPORTS:]))
    os.replace(tmp, path)


def report_id(mac: str, client: str, os_name: str) -> str:
    return hashlib.sha1(f"{mac or client}|{os_name}".encode()).hexdigest()[:12]


def record(path: Path, client: str, device: dict, body: str) -> dict:
    """Store a machine's report. One per machine and system; the newest replaces the older."""
    sections = parse_sections(body)
    summary = summarize(sections)
    entry = {
        "id": report_id(device.get("mac", ""), client, summary["os"]),
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ts": time.time(),
        "client": client,
        "mac": device.get("mac", ""),
        "device": " ".join(p for p in (device.get("manufacturer"), device.get("product")) if p),
        "summary": summary,
        "v": SUMMARY_VERSION,
        "sections": sections,
    }
    reports = [r for r in _load(path) if r.get("id") != entry["id"]]
    reports.append(entry)
    _save(path, reports)
    return entry


def _current(path: Path) -> List[dict]:
    """All reports, with summaries brought up to date (the text is kept, so it can be redone)."""
    reports = _load(path)
    changed = False
    for report in reports:
        if report.get("v") != SUMMARY_VERSION:
            report["summary"] = summarize(report.get("sections", {}))
            report["v"] = SUMMARY_VERSION
            changed = True
    if changed:
        _save(path, reports)
    return reports


def summaries(path: Path, mac: str = "") -> List[dict]:
    """Reports without their full text, newest first; only one machine's when a MAC is given."""
    items = [
        {k: v for k, v in r.items() if k != "sections"}
        for r in _current(path)
        if not mac or r.get("mac") == mac
    ]
    return sorted(items, key=lambda r: r.get("ts", 0), reverse=True)


def get(path: Path, report_id_: str) -> Optional[dict]:
    return next((r for r in _current(path) if r.get("id") == report_id_), None)


def delete(path: Path, report_id_: str) -> bool:
    reports = _load(path)
    kept = [r for r in reports if r.get("id") != report_id_]
    if len(kept) == len(reports):
        return False
    _save(path, kept)
    return True


# ---------------------------------------------------------------------------
# Finding out why a report did not arrive
# ---------------------------------------------------------------------------


def render_debug_script(host: str) -> str:
    """A read-only script for a person to run on the machine: it looks around and reports back."""
    url = f"http://{host}"
    if not _SAFE_URL.match(url + "/x"):
        url = ""  # only a plain host and port ever goes into a script
    return DEBUG_TEMPLATE.read_text().replace("__SERVER_URL__", url)


def record_debug(path: Path, client: str, text: str) -> None:
    entries = _load(path)
    entries.append(
        {
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "client": client,
            "text": clean(text)[: SECTION_LIMIT * 2],
        }
    )
    _save(path, entries[-MAX_DEBUG:])


def debug_reports(path: Path) -> List[dict]:
    return list(reversed(_load(path)))


# ---------------------------------------------------------------------------
# The layer for Ubuntu (casper)
# ---------------------------------------------------------------------------

_UNIT = """[Unit]
Description=iPXE Station boot report
ConditionKernelCommandLine=ipxe.report
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/ipxe-station-boot-report

[Install]
WantedBy=multi-user.target
"""


def layer_path(http_root: Path, folder: str) -> Path:
    return http_root / folder / LAYER_FILE


def build_layer(target: Path) -> None:
    """Make the squashfs layer: the collector, the service, and the link that starts it.

    The service only starts on a kernel command line that has ``ipxe.report``, so the layer can sit
    on the disk for every entry and only the ones that ask are affected.
    """
    if shutil.which("mksquashfs") is None:
        raise RuntimeError("mksquashfs is not available on this server")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "layer"
        (root / "usr/local/bin").mkdir(parents=True)
        (root / "etc/systemd/system/multi-user.target.wants").mkdir(parents=True)
        script = root / "usr/local/bin/ipxe-station-boot-report"
        script.write_text(COLLECTOR.read_text())
        script.chmod(0o755)
        (root / "etc/systemd/system" / LAYER_UNIT).write_text(_UNIT)
        os.symlink(
            f"/etc/systemd/system/{LAYER_UNIT}",
            root / "etc/systemd/system/multi-user.target.wants" / LAYER_UNIT,
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".tmp")
        part.unlink(missing_ok=True)
        done = subprocess.run(
            [
                "mksquashfs",
                str(root),
                str(part),
                "-noappend",
                "-all-root",
                "-comp",
                "gzip",
                "-quiet",
            ],
            capture_output=True,
            text=True,
        )
        if done.returncode != 0:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"mksquashfs failed: {done.stderr.strip()[:200]}")
        os.chmod(part, 0o644)
        os.replace(part, target)


def install_layer(http_root: Path, folder: str) -> Path:
    if not _FOLDER.match(folder):
        raise ValueError("invalid folder")
    target = layer_path(http_root, folder)
    build_layer(target)
    return target


def remove_layer(http_root: Path, folder: str) -> bool:
    target = layer_path(http_root, folder)
    if not target.exists():
        return False
    target.unlink()
    return True

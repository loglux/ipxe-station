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
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode

from .krd_firmware import parse_missing_firmware

HOOK_TEMPLATE = Path(__file__).with_name("boot_report_hook.sh")
HOOK_PATH = "/ipxe/live-report.sh"
REPORT_PATH = "/ipxe/boot-report"
HOOK_QUERY_FIELDS = ("mac", "manufacturer", "product")
DEFAULT_DELAY_SECONDS = 45
MEDIUM_HOOK_ARG = "live-config.hooks=medium"
MEDIUM_HOOK_FILE = "live/config-hooks/ipxe-station-report.sh"

MAX_BODY_BYTES = 300 * 1024
SECTION_LIMIT = 16 * 1024
TOTAL_LIMIT = 120 * 1024
MAX_REPORTS = 200

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
    return token == MEDIUM_HOOK_ARG or (
        token.startswith("live-config.hooks=") and HOOK_PATH in token
    )


# ---------------------------------------------------------------------------
# Two ways to get the script onto the machine
# ---------------------------------------------------------------------------
#
# By URL: live-config downloads it with wget, so the image needs wget (Debian 13's live image has
# curl only, and then live-config silently fetches nothing).
# From the medium: over NFS the extracted disk is the medium, and live-config runs the files in
# live/config-hooks/ of it (live-config.hooks=medium). No download, no wget.


def image_folder(kernel: str) -> Optional[str]:
    """The disk folder of an entry whose kernel is ``<folder>/live/vmlinuz``."""
    parts = (kernel or "").split("/")
    return parts[0] if len(parts) >= 3 and parts[1] == "live" and _FOLDER.match(parts[0]) else None


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
        "missing_firmware": sorted({m["name"] for m in missing}),
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
        "sections": sections,
    }
    reports = [r for r in _load(path) if r.get("id") != entry["id"]]
    reports.append(entry)
    _save(path, reports)
    return entry


def summaries(path: Path, mac: str = "") -> List[dict]:
    """Reports without their full text, newest first; only one machine's when a MAC is given."""
    items = [
        {k: v for k, v in r.items() if k != "sections"}
        for r in _load(path)
        if not mac or r.get("mac") == mac
    ]
    return sorted(items, key=lambda r: r.get("ts", 0), reverse=True)


def get(path: Path, report_id_: str) -> Optional[dict]:
    return next((r for r in _load(path) if r.get("id") == report_id_), None)


def delete(path: Path, report_id_: str) -> bool:
    reports = _load(path)
    kept = [r for r in reports if r.get("id") != report_id_]
    if len(kept) == len(reports):
        return False
    _save(path, kept)
    return True

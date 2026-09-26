"""Text size for Kaspersky Rescue Disk, decided on the server.

The disk's desktop (Cinnamon) shows text at 96 dpi, which is tiny on a 15 inch laptop with a Full HD
or better panel. A small script, made here for the machine that asks, runs early in the disk's
boot and sets the text scaling. The server decides the value: a default, overridden by rules for
particular models ("Latitude 5530 -> 150%"). The default "auto" lets the machine work it out from
its own screen.
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlencode

from pydantic import BaseModel, Field, field_validator

from .device_scenarios import MATCH_FIELDS, fields_match

HOOK_TEMPLATE = Path(__file__).with_name("krd_display_hook.sh")
HOOK_PATH = "/ipxe/krd-display.sh"
REPORT_PATH = "/ipxe/krd-report"
MIN_SCALE, MAX_SCALE = 1.0, 3.0

# Fields the boot line sends to the server, so rules can match on them.
HOOK_QUERY_FIELDS = ("mac", "manufacturer", "product", "sku", "family")

_NUMBER = re.compile(r"^\d(\.\d{1,2})?$")


def valid_scale(value: str) -> bool:
    if value in ("off", "auto"):
        return True
    return bool(_NUMBER.match(value)) and MIN_SCALE <= float(value) <= MAX_SCALE


def _check_scale(value: str) -> str:
    value = str(value).strip().lower()
    if not valid_scale(value):
        raise ValueError(f"'{value}' is not off, auto or a number from 1 to 3")
    return value


class DisplayRule(BaseModel):
    title: str = Field("", max_length=60)
    # field name -> pattern ("*" and "?" are wildcards, case does not matter)
    match: Dict[str, str] = Field(..., min_length=1)
    scale: str = "auto"

    model_config = {"extra": "forbid"}

    @field_validator("scale")
    @classmethod
    def _scale(cls, value: str) -> str:
        return _check_scale(value)

    @field_validator("match")
    @classmethod
    def _match(cls, value: Dict[str, str]) -> Dict[str, str]:
        for field, pattern in value.items():
            if field not in MATCH_FIELDS:
                raise ValueError(f"unknown match field '{field}'")
            if not isinstance(pattern, str) or not 1 <= len(pattern) <= 80:
                raise ValueError(f"match pattern for '{field}' must be 1-80 characters")
        return value


class DisplaySettings(BaseModel):
    default: str = "auto"
    # the boot script also tells the server which firmware the machine could not find
    report_firmware: bool = True
    rules: List[DisplayRule] = Field(default_factory=list, max_length=50)

    model_config = {"extra": "forbid"}

    @field_validator("default")
    @classmethod
    def _default(cls, value: str) -> str:
        return _check_scale(value)


def load_display_settings(path: Path) -> DisplaySettings:
    try:
        return DisplaySettings(**json.loads(path.read_text()))
    except (OSError, ValueError, TypeError):
        return DisplaySettings()


def save_display_settings(path: Path, settings: DisplaySettings) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings.model_dump(), indent=2))
    os.replace(tmp, path)


def resolve_scale(settings: DisplaySettings, device: dict) -> Tuple[str, str]:
    """The value for this machine and why: the first matching rule, else the default."""
    for rule in settings.rules:
        if fields_match(rule.match, device):
            return rule.scale, rule.title or "rule"
    return settings.default, "default"


def render_hook(scale: str, report_url: str = "") -> str:
    """The script the machine runs, with the server's decision written into it."""
    if not valid_scale(scale):
        scale = "off"  # never put an unchecked value into a script
    if report_url and not _SAFE_URL.match(report_url):
        report_url = ""  # nothing but a plain http URL ever goes into a script
    return (
        HOOK_TEMPLATE.read_text().replace("__SCALE__", scale).replace("__REPORT_URL__", report_url)
    )


_SAFE_URL = re.compile(r"^http://[A-Za-z0-9.\-:]+/[A-Za-z0-9/_.\-]*\?[A-Za-z0-9=&%+._\-]*$")


def report_url_for(host: str, device: dict) -> str:
    """Where the machine sends its firmware report, naming itself by MAC and model."""
    query = urlencode({k: device[k] for k in ("mac", "manufacturer", "product") if device.get(k)})
    return f"http://{host}{REPORT_PATH}?{query}"


def hook_argument() -> str:
    """The kernel argument that makes a live-config system fetch and run the script."""
    query = "&".join(
        [
            "mac=${net0/mac}",
            "manufacturer=${manufacturer:uristring}",
            "product=${product:uristring}",
            "sku=${smbios/1.25.0:uristring}",
            "family=${smbios/1.26.0:uristring}",
        ]
    )
    return f"live-config.hooks=http://${{server_ip}}:${{port}}{HOOK_PATH}?{query}"

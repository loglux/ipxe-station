"""Scenarios for specific machines.

A scenario says which machines it applies to (by what they report about themselves) and which
existing menu entry it points to. The server uses them to build the boot menu for the machine
that is asking: matching scenarios appear in a "Recommended for this device" block, and one
automatic scenario can be pre-selected with a countdown.
"""

import fnmatch
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, Set, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

from .ipxe_manager import DeviceMenu, DeviceRecommendation

logger = logging.getLogger(__name__)

# What a scenario may match on: fields the machine reports at network boot.
MATCH_FIELDS = (
    "manufacturer",
    "product",
    "sku",
    "family",
    "serial",
    "uuid",
    "mac",
    "platform",
    "arch",
    "nic_pci",
)

# Menu entry types that have a label to jump to.
TARGET_ENTRY_TYPES = {"boot", "chain", "submenu", "menu"}

AUTO_TIMEOUT_MS = 15000


class Scenario(BaseModel):
    id: str = Field(..., min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(..., min_length=1, max_length=60)
    description: str = Field("", max_length=200)
    # field name -> pattern; "*" and "?" are wildcards, case does not matter
    match: Dict[str, str] = Field(default_factory=dict)
    entry: str = Field(..., min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    mode: Literal["offer", "auto"] = "offer"
    enabled: bool = True

    model_config = {"extra": "forbid"}

    @field_validator("match")
    @classmethod
    def _check_match(cls, value: Dict[str, str]) -> Dict[str, str]:
        for field, pattern in value.items():
            if field not in MATCH_FIELDS:
                raise ValueError(
                    f"unknown match field '{field}' (allowed: {', '.join(MATCH_FIELDS)})"
                )
            if not isinstance(pattern, str) or not 1 <= len(pattern) <= 80:
                raise ValueError(f"match pattern for '{field}' must be 1-80 characters")
        return value

    @model_validator(mode="after")
    def _auto_needs_a_target(self):
        if self.mode == "auto" and not self.match:
            raise ValueError("an automatic scenario must say which machines it applies to")
        return self


def scenario_matches(scenario: Scenario, device: dict) -> bool:
    """True when every field of the rule matches what the machine reported."""
    for field, pattern in scenario.match.items():
        value = str(device.get(field) or "").lower()
        if not fnmatch.fnmatchcase(value, pattern.lower()):
            return False
    return True


def scenarios_for_device(
    scenarios: Iterable[Scenario], device: dict, entry_names: Set[str]
) -> List[Scenario]:
    """Enabled scenarios that match the machine and point to an entry that exists."""
    return [
        s for s in scenarios if s.enabled and s.entry in entry_names and scenario_matches(s, device)
    ]


def validate_scenarios(scenarios: List[Scenario], entry_names: Set[str]) -> List[str]:
    """Problems that stop a set of scenarios from being saved."""
    errors: List[str] = []
    seen: Set[str] = set()
    for scenario in scenarios:
        if scenario.id in seen:
            errors.append(f"{scenario.id}: duplicate id")
        seen.add(scenario.id)
        if scenario.entry not in entry_names:
            errors.append(
                f"{scenario.id}: menu entry '{scenario.entry}' does not exist or cannot be "
                "started (use a boot, chain or submenu entry)"
            )
    return errors


def load_scenarios(path: Path) -> List[Scenario]:
    """Read scenarios.json; a broken item is skipped so one mistake does not hide the rest."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return []
    items = data.get("scenarios", []) if isinstance(data, dict) else []
    scenarios: List[Scenario] = []
    for item in items:
        try:
            scenarios.append(Scenario(**item))
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping invalid scenario in %s: %s", path, exc)
    return scenarios


def save_scenarios(path: Path, scenarios: List[Scenario]) -> None:
    tmp = path.with_suffix(".json.tmp")
    payload = {"scenarios": [s.model_dump() for s in scenarios]}
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Text that ends up inside an iPXE script
# ---------------------------------------------------------------------------

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9 .,:/#()+_@-]")


def ipxe_safe_text(value, limit: int = 60) -> str:
    """Make a machine-supplied string safe to print from an iPXE script.

    The values come from the machine and cannot be trusted. iPXE treats "||", "&&" and "${...}"
    specially even inside echo arguments, so anything outside a small safe set becomes "?".
    """
    if not value:
        return ""
    text = _SAFE_CHARS.sub("?", " ".join(str(value).split()))
    return text[:limit]


def device_display_name(device: dict) -> str:
    """Brand and model as a person would say it (HP repeats its brand, Lenovo hides the name)."""
    maker = str(device.get("manufacturer") or "")
    product = str(device.get("product") or "")
    family = str(device.get("family") or "")
    word = re.split(r"[\s,.]+", maker)[0].lower() if maker else ""
    if word == "lenovo" and family:
        return f"{maker} {family}".strip()
    if word and product.lower().startswith(word):
        return product
    return " ".join(part for part in (maker, product) if part)


def build_device_menu(device: dict, matched: List[Scenario]) -> DeviceMenu:
    """What the personalised menu shows about this machine and which scenarios it recommends."""
    bios = " ".join(
        part
        for part in (
            device.get("bios_version"),
            f"({device['bios_date']})" if device.get("bios_date") else "",
        )
        if part
    )
    nic = " ".join(part for part in (device.get("nic_pci"), device.get("chip")) if part)
    boot_mode = " ".join(part for part in (device.get("platform"), device.get("arch")) if part)
    rows: List[Tuple[str, Optional[str]]] = [
        ("Brand", device.get("manufacturer")),
        ("Model", device.get("product")),
        ("Family", device.get("family")),
        ("SKU", device.get("sku")),
        ("Serial number", device.get("serial")),
        ("Asset tag", device.get("asset")),
        ("BIOS", bios),
        ("Network card", nic),
        ("MAC address", device.get("mac")),
        ("Boot mode", boot_mode),
        ("UUID", device.get("uuid")),
    ]
    info = [(label, ipxe_safe_text(value)) for label, value in rows if value]

    auto_taken = False
    recommendations: List[DeviceRecommendation] = []
    for scenario in matched:
        is_auto = scenario.mode == "auto" and not auto_taken
        auto_taken = auto_taken or is_auto
        recommendations.append(
            DeviceRecommendation(
                item=f"rec_{scenario.id}",
                title=scenario.title,
                target=scenario.entry,
                auto=is_auto,
            )
        )
    return DeviceMenu(
        name=ipxe_safe_text(device_display_name(device)) or "this machine",
        info=info,
        recommendations=recommendations,
        auto_timeout_ms=AUTO_TIMEOUT_MS,
    )

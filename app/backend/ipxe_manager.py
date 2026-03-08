"""
iPXE menu management for PXE Boot Station
Handles iPXE menu configuration generation, validation, and management
Enhanced with multiple Ubuntu boot options: netboot, live boot, rescue mode
REFACTORED: Using common utilities to eliminate repetition
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from pydantic import ValidationError

from .config import settings
from .ipxe_schema import IpxeMenuModel, menu_to_model, model_to_menu

# Import common utilities to eliminate repetition
from .utils import (
    safe_operation,
    safe_write_file,
    validate_file_path,
    validate_string_field,
)


@dataclass
class iPXEEntry:
    """Single iPXE menu entry with enhanced options"""

    name: str
    title: str
    kernel: Optional[str] = None
    initrd: Optional[str] = None
    cmdline: str = ""
    description: str = ""
    enabled: bool = True
    order: int = 0
    entry_type: str = "boot"  # boot, menu, action, separator, chain, submenu
    url: Optional[str] = None  # For HTTP boot entries
    boot_mode: str = "netboot"  # netboot, live, rescue, custom
    requires_iso: bool = False  # Whether this option needs ISO file
    requires_internet: bool = False  # Whether this option needs internet
    parent: Optional[str] = None  # parent menu name for submenu grouping
    preseed_profile: Optional[str] = None
    hiren_winpe_ready: bool = False
    hiren_bootmgr: Optional[str] = None
    hiren_bcd: Optional[str] = None
    hiren_boot_sdi: Optional[str] = None
    hiren_boot_wim: Optional[str] = None

    def __post_init__(self):
        """Validate entry after initialization"""
        if not self.name:
            raise ValueError("Entry name cannot be empty")
        if not self.title:
            self.title = self.name
        # Sanitize name for iPXE compatibility
        self.name = re.sub(r"[^a-zA-Z0-9_-]", "_", self.name)


@dataclass
class iPXEMenu:
    """Complete iPXE menu configuration"""

    title: str = "PXE Boot Station"
    timeout: int = 30000  # milliseconds
    default_entry: Optional[str] = None
    entries: List[iPXEEntry] = field(default_factory=list)
    header_text: str = ""
    footer_text: str = ""
    server_ip: str = ""  # filled by _apply_runtime_network_defaults from settings.json
    http_port: int = 0  # filled by _apply_runtime_network_defaults from settings.json

    def __post_init__(self):
        """Sort entries by order after initialization"""
        self.entries.sort(key=lambda x: (x.order, x.name))


class iPXEValidator:
    """iPXE configuration validation utilities"""

    ALLOWED_ENTRY_TYPES = {"boot", "menu", "action", "separator", "chain", "submenu"}
    ALLOWED_BOOT_MODES = {"netboot", "live", "rescue", "preseed", "tool", "custom", "boot"}
    REQUIRED_FILES = {
        "netboot": ("kernel", "initrd"),
        "rescue": ("kernel", "initrd"),
        "preseed": ("kernel", "initrd"),
        "live": ("kernel", "initrd", "iso"),
    }

    @staticmethod
    def validate_entry_name(name: str) -> Tuple[bool, str]:
        """Validate iPXE entry name using common utility"""
        return validate_string_field(
            name,
            field_name="Entry name",
            min_length=1,
            max_length=32,
            allowed_chars=r"^[a-zA-Z0-9_-]+$",
        )

    @staticmethod
    def validate_kernel_path(
        kernel: str, server_ip: str = settings.pxe_server_ip, port: int = settings.http_port
    ) -> Tuple[bool, str]:
        """Validate kernel path (file or URL)"""
        if not kernel:
            return False, "Kernel path cannot be empty"

        # Check if it's a URL
        if kernel.startswith(("http://", "https://", "tftp://")):
            try:
                parsed = urlparse(kernel)
                if not parsed.netloc:
                    return False, "Invalid URL format"
                return True, f"Valid URL: {kernel}"
            except Exception as e:
                return False, f"Invalid URL: {str(e)}"

        # Check if it's a local file path using common utility
        if kernel.startswith("/"):
            # Absolute path
            return validate_file_path(kernel, must_exist=True)
        else:
            # Relative path - assume it's served via HTTP
            full_url = f"http://{server_ip}:{port}/{kernel.lstrip('/')}"
            return True, f"Will be served as: {full_url}"

    @staticmethod
    def validate_timeout(timeout: int) -> Tuple[bool, str]:
        """Validate menu timeout"""
        if timeout < 0:
            return False, "Timeout cannot be negative"

        if timeout > 300000:  # 5 minutes
            return False, "Timeout cannot exceed 5 minutes (300000ms)"

        return True, f"Valid timeout: {timeout}ms ({timeout / 1000:.1f}s)"

    @staticmethod
    def validate_menu_title(title: str) -> Tuple[bool, str]:
        """Validate menu title using common utility"""
        return validate_string_field(title, field_name="Menu title", min_length=1, max_length=80)

    @classmethod
    @safe_operation("iPXE menu validation", return_tuple=True)
    def validate_menu(cls, menu: iPXEMenu) -> Tuple[bool, List[str]]:
        """Validate complete iPXE menu"""
        errors = []

        # Validate menu title using common utility
        is_valid, msg = cls.validate_menu_title(menu.title)
        if not is_valid:
            errors.append(f"Menu title: {msg}")

        # Check for duplicate entry names
        names = [entry.name for entry in menu.entries if entry.enabled]
        duplicates = set([name for name in names if names.count(name) > 1])
        if duplicates:
            errors.append(f"Duplicate entry names: {', '.join(duplicates)}")

        # Validate default entry exists
        if menu.default_entry:
            entry_names = [entry.name for entry in menu.entries if entry.enabled]
            if menu.default_entry not in entry_names:
                errors.append(f"Default entry '{menu.default_entry}' not found in menu")

        # Validate timeout
        is_valid, msg = cls.validate_timeout(menu.timeout)
        if not is_valid:
            errors.append(f"Timeout: {msg}")

        # Index for parent checks
        entry_by_name = {entry.name: entry for entry in menu.entries if entry.enabled}

        # Validate each entry
        for i, entry in enumerate(menu.entries):
            if not entry.enabled:
                continue

            # Entry type sanity
            if entry.entry_type not in cls.ALLOWED_ENTRY_TYPES:
                errors.append(
                    f"Entry {i + 1} ({entry.name}): Invalid entry_type '{entry.entry_type}'"
                )

            if (
                entry.entry_type not in ("submenu", "separator")
                and entry.boot_mode not in cls.ALLOWED_BOOT_MODES
            ):
                errors.append(
                    f"Entry {i + 1} ({entry.name}): Invalid boot_mode '{entry.boot_mode}'"
                )

            # Validate entry name
            is_valid, msg = cls.validate_entry_name(entry.name)
            if not is_valid:
                errors.append(f"Entry {i + 1} ({entry.name}): {msg}")

            # Validate entry title using common utility
            is_valid, msg = validate_string_field(
                entry.title, field_name="Entry title", min_length=1, max_length=60
            )
            if not is_valid:
                errors.append(f"Entry {i + 1} ({entry.name}) title: {msg}")

            # Validate kernel path for boot entries
            if entry.entry_type == "boot" and entry.kernel:
                is_valid, msg = cls.validate_kernel_path(
                    entry.kernel, menu.server_ip, menu.http_port
                )
                if not is_valid:
                    errors.append(f"Entry {i + 1} ({entry.name}) kernel: {msg}")
                if not entry.initrd:
                    errors.append(
                        f"Entry {i + 1} ({entry.name}): Boot entries should define initrd"
                    )
            elif entry.entry_type == "boot" and not entry.kernel:
                errors.append(f"Entry {i + 1} ({entry.name}): Boot entries must have a kernel path")
            elif entry.entry_type == "chain":
                if not entry.url:
                    errors.append(
                        f"Entry {i + 1} ({entry.name}): Chain entries require a URL/target"
                    )
                else:
                    parsed = urlparse(entry.url)
                    if not parsed.scheme:
                        errors.append(
                            f"Entry {i + 1} ({entry.name}): "
                            "Chain URL should include scheme (http/https/tftp)"
                        )
            elif entry.entry_type == "submenu":
                if not entry.title:
                    errors.append(f"Entry {i + 1} ({entry.name}): Submenu must have a title")

            # Parent validity (allow nested submenus and regular entries pointing to submenus)
            if entry.parent:
                if entry.parent not in entry_by_name:
                    errors.append(
                        f"Entry {i + 1} ({entry.name}): Parent '{entry.parent}' not found"
                    )
                else:
                    parent_entry = entry_by_name[entry.parent]
                    if parent_entry.entry_type not in {"submenu", "menu"}:
                        errors.append(
                            f"Entry {i + 1} ({entry.name}): "
                            f"Parent '{entry.parent}' is not a submenu/menu"
                        )

        # Cycle detection for parent relationships
        parents = {e.name: e.parent for e in menu.entries if e.enabled and e.parent}
        visited: Dict[str, str] = {}

        def visit(node: str) -> bool:
            if node not in parents:
                return False
            if visited.get(node) == "visiting":
                return True
            if visited.get(node) == "done":
                return False
            visited[node] = "visiting"
            parent = parents[node]
            has_cycle = visit(parent)
            visited[node] = "done"
            return has_cycle

        for name in parents:
            if visit(name):
                errors.append("Cycle detected in parent relationships; check submenu nesting")
                break

        # Schema validation (Pydantic) for storage/API contract
        try:
            menu_to_model(menu)
        except ValidationError as exc:
            for err in exc.errors():
                loc = " -> ".join(str(x) for x in err.get("loc", []))
                errors.append(f"Schema: {loc}: {err.get('msg')}")

        return len(errors) == 0, errors

    @classmethod
    def lint_menu(cls, menu: iPXEMenu, base_path: str = "/srv/http") -> List[str]:
        """Return non-fatal warnings about semantic issues."""
        warnings: List[str] = []

        if not menu.entries:
            warnings.append("Menu has no entries")

        if menu.timeout > 300000:
            warnings.append("Timeout exceeds 5 minutes")
        if menu.timeout == 0:
            warnings.append("Timeout is 0ms; menu will wait indefinitely")

        names = [entry.name for entry in menu.entries if entry.enabled]
        for name in set(names):
            if names.count(name) > 1:
                warnings.append(f"Duplicate entry '{name}'")

        for entry in menu.entries:
            if not entry.enabled:
                continue

            if entry.entry_type == "boot":
                cmdline = entry.cmdline or ""
                has_fetch_url = "fetch=" in cmdline or "url=" in cmdline
                if entry.boot_mode == "live" and not entry.requires_iso and not has_fetch_url:
                    warnings.append(
                        f"{entry.name}: live boot usually requires ISO (set requires_iso=True)"
                    )
                if entry.boot_mode == "preseed" and not entry.requires_internet:
                    warnings.append(
                        f"{entry.name}: preseed typically needs internet access "
                        "(set requires_internet=True)"
                    )
                if entry.requires_iso and entry.boot_mode not in {"live", "tool", "rescue"}:
                    warnings.append(
                        f"{entry.name}: requires_iso=True but boot_mode is '{entry.boot_mode}'"
                    )
                # File presence checks (best-effort, local paths only)
                warnings.extend(
                    cls._lint_local_files(
                        entry,
                        base_path,
                        menu.server_ip,
                        menu.http_port,
                    )
                )

        return warnings

    @staticmethod
    def _lint_local_files(
        entry: iPXEEntry,
        base_path: str,
        server_ip: str = "",
        http_port: int = 0,
    ) -> List[str]:
        """Check local file existence for kernel/initrd/ISO when applicable."""
        import re
        from pathlib import Path

        warnings: List[str] = []

        def is_url(path: str) -> bool:
            return path.startswith(("http://", "https://", "tftp://"))

        def resolve(path: Optional[str]) -> Optional[Path]:
            if not path:
                return None
            if is_url(path):
                return None
            if path.startswith("/"):
                return Path(path)
            return Path(base_path) / path.lstrip("/")

        def resolve_http_served_path(path: str) -> Path:
            normalized = path.lstrip("/")
            if normalized.startswith("http/"):
                normalized = normalized[len("http/") :]
            return Path(base_path) / normalized

        kernel_path = resolve(entry.kernel)
        initrd_path = resolve(entry.initrd)

        if kernel_path and not kernel_path.exists():
            warnings.append(f"{entry.name}: kernel file missing at {kernel_path}")
        if initrd_path and not initrd_path.exists():
            warnings.append(f"{entry.name}: initrd file missing at {initrd_path}")

        # ISO check:
        # - Skip NFS live mode (no local ISO required)
        # - Validate only explicit ISO references in cmdline (url=/fetch=/...iso)
        # - Warn only for concrete, locally-served ISO paths that are actually missing
        cmdline = entry.cmdline or ""
        cmdline_lower = cmdline.lower()
        is_nfs_live = "netboot=nfs" in cmdline_lower or "nfsroot=" in cmdline_lower
        needs_local_iso_check = (
            entry.requires_iso or entry.boot_mode == "live"
        ) and not is_nfs_live

        if needs_local_iso_check:
            iso_ref = None
            for match in re.finditer(r"(?:(?<=\s)|^)[^=\s]+=([^\s]+)", cmdline):
                candidate = match.group(1).strip("'\"")
                if ".iso" in candidate.lower():
                    iso_ref = candidate
                    break

            if iso_ref:
                local_path: Optional[Path] = None
                if iso_ref.startswith(("http://", "https://")):
                    parsed = urlparse(iso_ref)
                    host = (parsed.hostname or "").lower()
                    local_hosts = {
                        "localhost",
                        "127.0.0.1",
                        "::1",
                        settings.pxe_server_ip.lower(),
                    }
                    if server_ip:
                        local_hosts.add(server_ip.lower())
                    if "${server_ip}" in iso_ref:
                        local_path = resolve_http_served_path(parsed.path)
                    elif host in local_hosts and parsed.path:
                        if http_port and parsed.port and parsed.port != http_port:
                            local_path = None
                        else:
                            local_path = resolve_http_served_path(parsed.path)
                elif iso_ref.startswith("tftp://"):
                    local_path = None
                elif iso_ref.startswith("/http/"):
                    local_path = resolve_http_served_path(iso_ref)
                elif iso_ref.startswith("/"):
                    local_path = Path(iso_ref)
                else:
                    local_path = resolve_http_served_path(iso_ref)

                if local_path and not local_path.exists():
                    warnings.append(f"{entry.name}: ISO missing at {local_path}")

        # HTTP-served distros: check that the extracted ISO content directory exists.
        # Each entry maps (cmdline marker, URL regex, required subdir, display name).
        # Add a new row here when supporting a new distro type.
        _HTTP_CONTENT_CHECKS = [
            (
                "archiso_http_srv=",
                r"archiso_http_srv=\S+?/http/(rescue-[\d.]+)/?",
                "sysresccd",
                "SystemRescue",
            ),
            (
                "netboot=",
                r"netboot=\S+?/http/(kaspersky-[\w.]+)/?",
                "krd",
                "Kaspersky",
            ),
        ]
        for marker, pattern, subdir, label in _HTTP_CONTENT_CHECKS:
            if marker not in cmdline:
                continue
            m = re.search(pattern, cmdline)
            if not m:
                continue
            content_dir = Path(base_path) / m.group(1) / subdir
            if not content_dir.exists():
                warnings.append(
                    f"{entry.name}: {label} content missing at {content_dir}"
                    " — download and extract ISO first"
                )

        return warnings


class UbuntuBootModes:
    """Ubuntu boot mode configurations"""

    @staticmethod
    def get_netboot_config(version: str, server_ip: str, port: int) -> Dict[str, str]:
        """Get netboot configuration (internet installation)"""
        base_url = f"http://{server_ip}:{port}/http/ubuntu-{version}"

        configs = {
            "24.04": {
                "kernel": f"{base_url}/vmlinuz",
                "initrd": f"{base_url}/initrd",
                "cmdline": "ip=dhcp url=http://archive.ubuntu.com/ubuntu/dists/noble/main/installer-amd64/current/legacy-images/netboot/ auto=true",  # noqa: E501
                "description": "Network installation from Ubuntu repositories",
            },
            "22.04": {
                "kernel": f"{base_url}/vmlinuz",
                "initrd": f"{base_url}/initrd",
                "cmdline": "ip=dhcp url=http://archive.ubuntu.com/ubuntu/dists/jammy/main/installer-amd64/current/legacy-images/netboot/ auto=true",  # noqa: E501
                "description": "Network installation from Ubuntu repositories",
            },
            "20.04": {
                "kernel": f"{base_url}/vmlinuz",
                "initrd": f"{base_url}/initrd",
                "cmdline": "ip=dhcp url=http://archive.ubuntu.com/ubuntu/dists/focal/main/installer-amd64/current/legacy-images/netboot/ auto=true",  # noqa: E501
                "description": "Network installation from Ubuntu repositories",
            },
        }

        return configs.get(version, configs["22.04"])  # Default to 22.04

    @staticmethod
    def get_live_config(version: str, server_ip: str, port: int) -> Dict[str, str]:
        """Get live boot configuration (requires ISO)"""
        base_url = f"http://{server_ip}:{port}/ubuntu-{version}"

        return {
            "kernel": f"{base_url}/vmlinuz",
            "initrd": f"{base_url}/initrd",
            "cmdline": f"ip=dhcp boot=casper netboot=url url={base_url}/ubuntu-{version}-live-server-amd64.iso quiet splash",  # noqa: E501
            "description": "Live boot from local ISO file",
        }

    @staticmethod
    def get_rescue_config(version: str, server_ip: str, port: int) -> Dict[str, str]:
        """Get rescue mode configuration"""
        base_url = f"http://{server_ip}:{port}/ubuntu-{version}"

        return {
            "kernel": f"{base_url}/vmlinuz",
            "initrd": f"{base_url}/initrd",
            "cmdline": "ip=dhcp rescue/enable=true single",
            "description": "Rescue and recovery mode",
        }

    @staticmethod
    def get_preseed_config(version: str, server_ip: str, port: int) -> Dict[str, str]:
        """Get automated preseed installation"""
        base_url = f"http://{server_ip}:{port}/ubuntu-{version}"

        return {
            "kernel": f"{base_url}/vmlinuz",
            "initrd": f"{base_url}/initrd",
            "cmdline": f"ip=dhcp auto=true url={base_url}/preseed.cfg locale=en_US console-setup/ask_detect=false keyboard-configuration/xkb-keymap=us",  # noqa: E501
            "description": "Automated installation with preseed configuration",
        }


class UbuntuVersionDetector:
    """Detect available Ubuntu versions and their capabilities"""

    @staticmethod
    def scan_available_versions(base_path: str = "/srv/http") -> Dict[str, Dict[str, bool]]:
        """Scan for available Ubuntu versions and their files"""
        base_dir = Path(base_path)
        versions = {}

        if not base_dir.exists():
            return versions

        # Look for ubuntu-* directories
        for ubuntu_dir in base_dir.iterdir():
            if not ubuntu_dir.is_dir() or not ubuntu_dir.name.startswith("ubuntu-"):
                continue

            version = ubuntu_dir.name.replace("ubuntu-", "")

            # Check for required and optional files
            capabilities = {
                "kernel": (ubuntu_dir / "vmlinuz").exists(),
                "initrd": (ubuntu_dir / "initrd").exists(),
                "iso": (ubuntu_dir / f"ubuntu-{version}-live-server-amd64.iso").exists(),
                "preseed": (ubuntu_dir / "preseed.cfg").exists(),
            }

            # Only include if basic files exist
            if capabilities["kernel"] and capabilities["initrd"]:
                versions[version] = capabilities

        return versions

    @staticmethod
    def get_boot_options_for_version(version: str, capabilities: Dict[str, bool]) -> List[str]:
        """Get available boot options for a specific Ubuntu version"""
        options = []

        # Always available if kernel+initrd exist
        if capabilities.get("kernel") and capabilities.get("initrd"):
            options.append("netboot")
            options.append("rescue")

        # Available if preseed exists
        if capabilities.get("preseed"):
            options.append("preseed")

        # Available if ISO exists
        if capabilities.get("iso"):
            options.append("live")

        return options


class iPXEGenerator:
    """iPXE menu file generators"""

    @staticmethod
    def _menu_label(name: Optional[str]) -> str:
        return "start" if name is None else f"submenu_{name}"

    @staticmethod
    def _build_children_map(entries: List[iPXEEntry]) -> Dict[Optional[str], List[iPXEEntry]]:
        """Group enabled entries by parent."""
        from collections import defaultdict

        children: Dict[Optional[str], List[iPXEEntry]] = defaultdict(list)
        for entry in entries:
            if not entry.enabled:
                continue
            parent = entry.parent or None
            children[parent].append(entry)

        for lst in children.values():
            lst.sort(key=lambda e: (e.order, e.name))
        return children

    @classmethod
    def _render_menu_block(
        cls,
        current: Optional[str],
        title: str,
        menu: iPXEMenu,
        children_map: Dict[Optional[str], List[iPXEEntry]],
        parent_map: Dict[str, Optional[str]],
        back_labels: List[Tuple[str, str]],
    ) -> List[str]:
        """Render a menu (root or submenu) with its children."""
        lines: List[str] = []
        label = cls._menu_label(current)
        lines.extend(
            [
                f":{label}",
                f"menu {title}",
                "item --gap -- -------------------------------",
            ]
        )

        if current is not None:
            # Add back navigation
            back_item = f"back_{current}"
            parent_label = cls._menu_label(parent_map.get(current))
            lines.append(f"item {back_item} <-- Back")
            back_labels.append((back_item, parent_label))

        children = children_map.get(current, [])
        for entry in children:
            if entry.entry_type == "separator":
                lines.append(f"item --gap -- {entry.title}")
            elif entry.entry_type == "boot":
                mode_indicator = {
                    "netboot": "[NET]",
                    "live": "[LIVE]",
                    "rescue": "[RESCUE]",
                    "preseed": "[AUTO]",
                    "tool": "[TOOL]",
                }.get(entry.boot_mode, "[BOOT]")
                lines.append(f"item {entry.name} {mode_indicator} {entry.title}")
            elif entry.entry_type in {"menu", "submenu"}:
                lines.append(f"item {entry.name} {entry.title} -->")
            elif entry.entry_type == "action":
                lines.append(f"item {entry.name} {entry.title}")
            elif entry.entry_type == "chain":
                lines.append(f"item {entry.name} [CHAIN] {entry.title}")

        if current is None:
            lines.extend(
                [
                    "item --gap --",
                    "item shell [SHELL]  Drop to iPXE shell",
                    "item reboot [REBOOT] Reboot computer",
                    "item exit [EXIT] Exit to BIOS",
                ]
            )

        default_for_menu = (
            menu.default_entry
            if current is None and any(e.name == menu.default_entry for e in children)
            else None
        )

        if default_for_menu:
            lines.append(
                f"choose --default {default_for_menu} --timeout {menu.timeout} target && goto ${{target}}"  # noqa: E501
            )
        else:
            lines.append(
                f"choose --timeout {menu.timeout if current is None else 0} target && goto ${{target}}"  # noqa: E501
            )

        lines.append("")

        # Render nested submenus recursively
        for entry in children:
            if entry.entry_type in {"submenu", "menu"}:
                lines.extend(
                    cls._render_menu_block(
                        entry.name, entry.title, menu, children_map, parent_map, back_labels
                    )
                )

        return lines

    @staticmethod
    def generate_ipxe_script(menu: iPXEMenu) -> str:
        """Generate iPXE script content with enhanced multi-mode support"""
        script_lines = [
            "#!ipxe",
            "",
            "# iPXE Boot Menu - Enhanced Multi-Mode Support",
            "# Generated by PXE Boot Station",
            "",
        ]

        # Add header text if provided
        if menu.header_text:
            script_lines.extend(
                [f"echo {iPXEGenerator._escape_echo_text(menu.header_text)}", "sleep 2", ""]
            )

        children_map = iPXEGenerator._build_children_map(menu.entries)
        parent_map = {entry.name: entry.parent for entry in menu.entries if entry.enabled}
        back_labels: List[Tuple[str, str]] = []
        script_lines.extend(
            iPXEGenerator._render_menu_block(
                None, menu.title, menu, children_map, parent_map, back_labels
            )
        )

        # Generate sections for each entry
        for entry in menu.entries:
            if not entry.enabled:
                continue

            if entry.entry_type == "boot" and entry.kernel:
                script_lines.extend(
                    [
                        f":{entry.name}",
                        f"echo Booting {iPXEGenerator._escape_echo_text(entry.title)}...",
                    ]
                )

                # Add description and requirements info
                if entry.description:
                    script_lines.append(
                        f"echo {iPXEGenerator._escape_echo_text(entry.description)}"
                    )

                if entry.requires_internet:
                    script_lines.append("echo Note: Internet connection required")

                if entry.requires_iso:
                    script_lines.append("echo Note: Local ISO file required")

                # Canonical WinPE flow via wimboot:
                # kernel wimboot
                # initrd <bootmgr> bootmgr
                # initrd <BCD> BCD
                # initrd <boot.sdi> boot.sdi
                # initrd <boot.wim> boot.wim
                if entry.hiren_winpe_ready and entry.kernel:
                    kernel_url = iPXEGenerator._resolve_kernel_url(
                        entry.kernel, menu.server_ip, menu.http_port
                    )
                    cmdline = (
                        (entry.cmdline or "")
                        .replace("${server_ip}", menu.server_ip)
                        .replace("${port}", str(menu.http_port))
                    )
                    script_lines.append(f"kernel {kernel_url} {cmdline}".strip())

                    if entry.hiren_bootmgr:
                        bootmgr_url = iPXEGenerator._resolve_kernel_url(
                            entry.hiren_bootmgr, menu.server_ip, menu.http_port
                        )
                        script_lines.append(f"initrd {bootmgr_url} bootmgr")
                    if entry.hiren_bcd:
                        bcd_url = iPXEGenerator._resolve_kernel_url(
                            entry.hiren_bcd, menu.server_ip, menu.http_port
                        )
                        script_lines.append(f"initrd {bcd_url} BCD")
                    if entry.hiren_boot_sdi:
                        sdi_url = iPXEGenerator._resolve_kernel_url(
                            entry.hiren_boot_sdi, menu.server_ip, menu.http_port
                        )
                        script_lines.append(f"initrd {sdi_url} boot.sdi")
                    boot_wim_path = entry.hiren_boot_wim or entry.initrd
                    if boot_wim_path:
                        wim_url = iPXEGenerator._resolve_kernel_url(
                            boot_wim_path, menu.server_ip, menu.http_port
                        )
                        script_lines.append(f"initrd {wim_url} boot.wim")

                    script_lines.extend(["boot", "goto start", ""])
                    continue

                # Determine kernel URL
                if entry.kernel:
                    kernel_url = iPXEGenerator._resolve_kernel_url(
                        entry.kernel, menu.server_ip, menu.http_port
                    )
                    # Substitute variables in cmdline (${server_ip}, ${port})
                    cmdline = entry.cmdline if entry.cmdline else ""
                    cmdline = cmdline.replace("${server_ip}", menu.server_ip).replace(
                        "${port}", str(menu.http_port)
                    )
                    script_lines.append(f"kernel {kernel_url} {cmdline}".strip())

                # Add initrd if provided
                if entry.initrd:
                    initrd_url = iPXEGenerator._resolve_kernel_url(
                        entry.initrd, menu.server_ip, menu.http_port
                    )
                    script_lines.append(f"initrd {initrd_url}")

                script_lines.extend(["boot", "goto start", ""])

            elif entry.entry_type == "chain" and entry.url:
                script_lines.extend(
                    [
                        f":{entry.name}",
                        f"echo Chaining to {iPXEGenerator._escape_echo_text(entry.title)}...",
                    ]
                )
                chain_target = iPXEGenerator._resolve_kernel_url(
                    entry.url, menu.server_ip, menu.http_port
                )
                script_lines.extend([f"chain {chain_target}", "goto start", ""])
            elif entry.entry_type in {"submenu", "menu"}:
                script_lines.extend(
                    [f":{entry.name}", f"goto {iPXEGenerator._menu_label(entry.name)}", ""]
                )

        # Back navigation labels for submenus
        for back_item, target_label in back_labels:
            script_lines.extend([f":{back_item}", f"goto {target_label}", ""])

        # Standard menu actions
        script_lines.extend(
            [
                ":shell",
                "echo Dropping to iPXE shell...",
                "shell",
                "",
                ":reboot",
                "echo Rebooting in 3 seconds...",
                "sleep 3",
                "reboot",
                "",
                ":exit",
                "echo Exiting to BIOS...",
                "exit",
                "",
                ":error",
                "echo Boot failed, returning to menu...",
                "sleep 3",
                "goto start",
            ]
        )

        # Add footer text if provided
        if menu.footer_text:
            script_lines.extend(
                [
                    "",
                    f"echo {iPXEGenerator._escape_echo_text(menu.footer_text)}",
                ]
            )

        return "\n".join(script_lines)

    @staticmethod
    def _resolve_kernel_url(path: str, server_ip: str, port: int) -> str:
        """Resolve kernel path to full URL"""
        if not path:
            return ""
        if path.startswith(("http://", "https://", "tftp://")):
            return path
        elif path.startswith("/"):
            # Absolute path - convert to HTTP URL
            return f"http://{server_ip}:{port}{path}"
        else:
            # Relative path - assets are served under /http/ mount point
            return f"http://{server_ip}:{port}/http/{path.lstrip('/')}"

    @staticmethod
    def _escape_echo_text(text: str) -> str:
        """
        Escape text for safe use in iPXE echo statements.

        - Replaces newlines with spaces (iPXE echo doesn't support multiline)
        - Escapes ${} to prevent variable expansion
        - Strips control characters
        """
        if not text:
            return ""

        # Replace newlines and other control chars with space
        text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")

        # Escape ${} variable expansion by replacing $ with $$
        # (iPXE uses $$ to represent literal $)
        text = text.replace("${", "$${")

        # Remove other control characters
        text = "".join(char if char.isprintable() or char == " " else " " for char in text)

        # Collapse multiple spaces
        import re

        text = re.sub(r"\s+", " ", text).strip()

        return text

    @staticmethod
    def _escape_grub_single_quoted(text: str) -> str:
        """
        Escape text for use in GRUB single-quoted strings.

        In GRUB, single quotes prevent variable expansion but don't escape
        single quotes themselves. To include a literal single quote, use: '\''

        Example: "It's test" -> "It'\''s test"
        """
        if not text:
            return ""

        # Replace single quote with '\'' (end quote, escaped quote, start quote)
        text = text.replace("'", "'\\''")

        # Remove control characters (newlines, tabs, etc.)
        text = "".join(char if char.isprintable() or char == " " else " " for char in text)

        # Collapse multiple spaces
        import re

        text = re.sub(r"\s+", " ", text).strip()

        return text

    @staticmethod
    def _escape_grub_argument(text: str) -> str:
        """
        Escape text for use as GRUB command argument (kernel, initrd paths, cmdline).

        Escapes shell special characters that could cause issues in GRUB commands.
        Note: Spaces are NOT escaped as they're natural argument separators in cmdline.
        """
        if not text:
            return ""

        # Remove newlines and control characters (replace with space)
        text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        text = "".join(char if char.isprintable() or char == " " else " " for char in text)

        # Escape shell special characters with backslash
        # Characters that need escaping in GRUB: $, `, \, ", ;, &, |, <, >, (, ), {, }
        # Note: Space is NOT escaped as it's the natural separator for kernel arguments
        special_chars = ["$", "`", "\\", '"', ";", "&", "|", "<", ">", "(", ")", "{", "}"]
        for char in special_chars:
            text = text.replace(char, "\\" + char)

        # Collapse multiple spaces
        import re

        text = re.sub(r"\s+", " ", text).strip()

        return text

    @staticmethod
    def generate_grub_config(menu: iPXEMenu) -> str:
        """Generate GRUB configuration (for comparison/fallback)"""
        grub_lines = [
            "# GRUB Configuration",
            "# Generated by PXE Boot Station",
            "",
            f"set timeout={menu.timeout // 1000}",
            "set default=0",
            "",
        ]

        boot_entries = [
            entry for entry in menu.entries if entry.enabled and entry.entry_type == "boot"
        ]

        for i, entry in enumerate(boot_entries):
            # Escape title for single-quoted strings
            escaped_title = iPXEGenerator._escape_grub_single_quoted(entry.title)

            # Escape kernel path and cmdline for command arguments
            escaped_kernel = (
                iPXEGenerator._escape_grub_argument(entry.kernel) if entry.kernel else ""
            )
            escaped_cmdline = (
                iPXEGenerator._escape_grub_argument(entry.cmdline) if entry.cmdline else ""
            )

            grub_lines.extend(
                [
                    f"menuentry '{escaped_title}' {{",
                    f"    echo 'Loading {escaped_title}...'",
                    f"    linux {escaped_kernel} {escaped_cmdline}".strip(),
                ]
            )

            if entry.initrd:
                escaped_initrd = iPXEGenerator._escape_grub_argument(entry.initrd)
                grub_lines.append(f"    initrd {escaped_initrd}")

            grub_lines.extend(["}", ""])

        return "\n".join(grub_lines)


class iPXETemplateManager:
    """Pre-defined iPXE menu templates with enhanced multi-mode support"""

    @staticmethod
    def get_ubuntu_template(
        server_ip: str = settings.pxe_server_ip, port: int = settings.http_port
    ) -> iPXEMenu:
        """Original Ubuntu installation template"""
        entries = [
            iPXEEntry(
                name="ubuntu_install",
                title="Install Ubuntu 22.04 LTS",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                cmdline="ip=dhcp url=http://{server_ip}:{port}/ubuntu/ubuntu-22.04-live-server-amd64.iso autoinstall ds=nocloud-net;s=http://{server_ip}:{port}/cloud-init/",  # noqa: E501
                description="Automated Ubuntu Server installation",
                order=1,
            ),
            iPXEEntry(
                name="ubuntu_live",
                title="Ubuntu 22.04 Live Session",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                cmdline="ip=dhcp boot=casper netboot=nfs nfsroot={server_ip}:/srv/nfs/ubuntu",
                description="Live Ubuntu session without installation",
                order=2,
            ),
            iPXEEntry(
                name="ubuntu_rescue",
                title="Ubuntu Rescue Mode",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                cmdline="ip=dhcp rescue/enable=true",
                description="Ubuntu rescue and recovery mode",
                order=3,
            ),
        ]

        # Format cmdline with actual server IP and port
        for entry in entries:
            entry.cmdline = (entry.cmdline or "").format(server_ip=server_ip, port=port)

        return iPXEMenu(
            title="Ubuntu PXE Boot Menu",
            timeout=30000,
            default_entry="ubuntu_install",
            entries=entries,
            server_ip=server_ip,
            http_port=port,
            header_text="Welcome to Ubuntu PXE Boot Station",
            footer_text="Use arrow keys to navigate, Enter to select",
        )

    @staticmethod
    def get_ubuntu_multi_template(
        server_ip: str = settings.pxe_server_ip,
        port: int = settings.http_port,
        available_versions: List[str] = None,
    ) -> iPXEMenu:
        """Enhanced Ubuntu template with multiple boot options per version"""

        if available_versions is None:
            # Auto-detect available versions
            detector = UbuntuVersionDetector()
            available_versions = list(detector.scan_available_versions().keys())
            if not available_versions:
                available_versions = ["24.04", "22.04", "20.04"]

        entries = []
        order = 1

        # Header separator
        entries.append(
            iPXEEntry(
                name="ubuntu_header",
                title="Ubuntu Installation Options",
                entry_type="separator",
                order=order,
            )
        )
        order += 1

        # Generate entries for each available Ubuntu version
        for version in available_versions:
            # Check if files exist for this version
            version_path = Path(f"/srv/http/ubuntu-{version}")
            iso_path = version_path / f"ubuntu-{version}-live-server-amd64.iso"
            kernel_path = version_path / "vmlinuz"
            initrd_path = version_path / "initrd"
            preseed_path = version_path / "preseed.cfg"

            files_exist = kernel_path.exists() and initrd_path.exists()
            iso_exists = iso_path.exists()
            preseed_exists = preseed_path.exists()

            if not files_exist:
                continue  # Skip if basic files don't exist

            # Ubuntu version separator
            entries.append(
                iPXEEntry(
                    name=f"separator_ubuntu_{version.replace('.', '_')}",
                    title=f"── Ubuntu {version} LTS ──",
                    entry_type="separator",
                    order=order,
                )
            )
            order += 1

            # 1. Netboot installation (always available if kernel+initrd exist)
            netboot_config = UbuntuBootModes.get_netboot_config(version, server_ip, port)
            entries.append(
                iPXEEntry(
                    name=f"ubuntu_{version.replace('.', '_')}_netboot",
                    title=f"Ubuntu {version} - Network Install",
                    kernel=netboot_config["kernel"],
                    initrd=netboot_config["initrd"],
                    cmdline=netboot_config["cmdline"],
                    description=netboot_config["description"],
                    order=order,
                    boot_mode="netboot",
                    requires_iso=False,
                    requires_internet=True,
                )
            )
            order += 1

            # 2. Live boot (only if ISO exists)
            if iso_exists:
                live_config = UbuntuBootModes.get_live_config(version, server_ip, port)
                entries.append(
                    iPXEEntry(
                        name=f"ubuntu_{version.replace('.', '_')}_live",
                        title=f"Ubuntu {version} - Live Boot",
                        kernel=live_config["kernel"],
                        initrd=live_config["initrd"],
                        cmdline=live_config["cmdline"],
                        description=live_config["description"],
                        order=order,
                        boot_mode="live",
                        requires_iso=True,
                        requires_internet=False,
                    )
                )
                order += 1

            # 3. Preseed installation (only if preseed.cfg exists)
            if preseed_exists:
                preseed_config = UbuntuBootModes.get_preseed_config(version, server_ip, port)
                entries.append(
                    iPXEEntry(
                        name=f"ubuntu_{version.replace('.', '_')}_preseed",
                        title=f"Ubuntu {version} - Auto Install",
                        kernel=preseed_config["kernel"],
                        initrd=preseed_config["initrd"],
                        cmdline=preseed_config["cmdline"],
                        description=preseed_config["description"],
                        order=order,
                        boot_mode="preseed",
                        requires_iso=False,
                        requires_internet=True,
                    )
                )
                order += 1

            # 4. Rescue mode (always available)
            rescue_config = UbuntuBootModes.get_rescue_config(version, server_ip, port)
            entries.append(
                iPXEEntry(
                    name=f"ubuntu_{version.replace('.', '_')}_rescue",
                    title=f"Ubuntu {version} - Rescue Mode",
                    kernel=rescue_config["kernel"],
                    initrd=rescue_config["initrd"],
                    cmdline=rescue_config["cmdline"],
                    description=rescue_config["description"],
                    order=order,
                    boot_mode="rescue",
                    requires_iso=False,
                    requires_internet=False,
                )
            )
            order += 1

        # Tools separator
        entries.append(
            iPXEEntry(
                name="tools_header", title="System Tools", entry_type="separator", order=order
            )
        )
        order += 1

        # Memory test
        entries.append(
            iPXEEntry(
                name="memtest",
                title="Memory Test (Memtest86+)",
                kernel="tools/memtest86+.bin",
                description="Test system memory for errors",
                order=order,
                boot_mode="tool",
                entry_type="boot",
            )
        )

        # Set default to first netboot option
        default_entry = None
        for entry in entries:
            if entry.entry_type == "boot" and entry.boot_mode == "netboot":
                default_entry = entry.name
                break

        return iPXEMenu(
            title="Ubuntu Multi-Mode PXE Boot",
            timeout=45000,
            default_entry=default_entry,
            entries=entries,
            server_ip=server_ip,
            http_port=port,
            header_text="Multiple Ubuntu Installation Options Available",
            footer_text="Use arrow keys to navigate, Enter to select",
        )

    @staticmethod
    def get_quick_ubuntu_template(
        server_ip: str = settings.pxe_server_ip, port: int = settings.http_port
    ) -> iPXEMenu:
        """Quick Ubuntu template with just netboot options"""

        available_versions = []

        # Auto-detect available versions
        for version in ["24.04", "22.04", "20.04"]:
            version_path = Path(f"/srv/http/ubuntu-{version}")
            if (version_path / "vmlinuz").exists() and (version_path / "initrd").exists():
                available_versions.append(version)

        entries = []
        order = 1

        for version in available_versions:
            netboot_config = UbuntuBootModes.get_netboot_config(version, server_ip, port)
            entries.append(
                iPXEEntry(
                    name=f"ubuntu_{version.replace('.', '_')}",
                    title=f"Ubuntu {version} LTS",
                    kernel=netboot_config["kernel"],
                    initrd=netboot_config["initrd"],
                    cmdline=netboot_config["cmdline"],
                    description=f"Install Ubuntu {version} from network",
                    order=order,
                    boot_mode="netboot",
                )
            )
            order += 1

        return iPXEMenu(
            title="Ubuntu Quick Install",
            timeout=30000,
            default_entry=entries[0].name if entries else None,
            entries=entries,
            server_ip=server_ip,
            http_port=port,
            header_text="Quick Ubuntu Network Installation",
            footer_text="Select Ubuntu version to install",
        )

    @staticmethod
    def get_diagnostic_template(
        server_ip: str = settings.pxe_server_ip, port: int = settings.http_port
    ) -> iPXEMenu:
        """System diagnostic tools template"""
        entries = [
            iPXEEntry(
                name="memtest",
                title="Memory Test (Memtest86+)",
                kernel="tools/memtest86+.bin",
                description="Test system memory for errors",
                order=1,
            ),
            iPXEEntry(
                name="hdparm",
                title="Hard Drive Diagnostics",
                kernel="tools/hdparm.img",
                description="Hard drive testing and diagnostics",
                order=2,
            ),
            iPXEEntry(
                name="dban",
                title="DBAN - Disk Wipe Utility",
                kernel="tools/dban.img",
                description="Secure disk wiping utility",
                order=3,
            ),
        ]

        return iPXEMenu(
            title="System Diagnostic Tools",
            timeout=60000,
            entries=entries,
            server_ip=server_ip,
            http_port=port,
            header_text="System Diagnostic and Repair Tools",
            footer_text="WARNING: Some tools may modify or erase data!",
        )

    @staticmethod
    def get_multi_os_template(
        server_ip: str = settings.pxe_server_ip, port: int = settings.http_port
    ) -> iPXEMenu:
        """Multi-OS boot template"""
        entries = [
            iPXEEntry(
                name="separator1", title="Linux Distributions", entry_type="separator", order=1
            ),
            iPXEEntry(
                name="ubuntu",
                title="Ubuntu 22.04 LTS",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                cmdline="ip=dhcp",
                order=2,
            ),
            iPXEEntry(
                name="centos",
                title="CentOS Stream 9",
                kernel="centos/vmlinuz",
                initrd="centos/initrd.img",
                cmdline="ip=dhcp inst.repo=http://{server_ip}:{port}/centos/",
                order=3,
            ),
            iPXEEntry(name="separator2", title="Utilities", entry_type="separator", order=4),
            iPXEEntry(
                name="clonezilla",
                title="Clonezilla Live",
                kernel="clonezilla/vmlinuz",
                initrd="clonezilla/initrd.img",
                cmdline='boot=live config noswap nolocales edd=on ocs_live_run="ocs-live-general"',
                order=5,
            ),
            iPXEEntry(
                name="gparted",
                title="GParted Live",
                kernel="gparted/vmlinuz",
                initrd="gparted/initrd.img",
                cmdline="boot=live config union=overlay username=user noswap noeject ip= vga=788",
                order=6,
            ),
        ]

        # Format cmdline with actual server IP and port
        for entry in entries:
            if entry.cmdline:
                entry.cmdline = (entry.cmdline or "").format(server_ip=server_ip, port=port)

        return iPXEMenu(
            title="Multi-OS PXE Boot Menu",
            timeout=45000,
            default_entry="ubuntu",
            entries=entries,
            server_ip=server_ip,
            http_port=port,
            header_text="Multiple Operating Systems and Tools",
            footer_text="Select an option or wait for default selection",
        )


class iPXEManager:
    """Main iPXE menu management class with enhanced capabilities"""

    def __init__(self, config_path: str = "/srv/ipxe/boot.ipxe"):
        self.config_path = Path(config_path)
        self.validator = iPXEValidator()
        self.generator = iPXEGenerator()
        self.templates = iPXETemplateManager()
        self.detector = UbuntuVersionDetector()

    @safe_operation("iPXE menu creation")
    def create_menu(
        self,
        title: str = "PXE Boot Menu",
        server_ip: str = settings.pxe_server_ip,
        port: int = settings.http_port,
    ) -> iPXEMenu:
        """Create new empty iPXE menu"""
        return iPXEMenu(title=title, server_ip=server_ip, http_port=port)

    @safe_operation("iPXE entry addition", return_tuple=True)
    def add_entry(self, menu: iPXEMenu, entry: iPXEEntry) -> Tuple[bool, str]:
        """Add entry to menu"""
        # Validate entry using common utility
        is_valid, msg = self.validator.validate_entry_name(entry.name)
        if not is_valid:
            return False, f"Invalid entry: {msg}"

        # Check for duplicates
        existing_names = [e.name for e in menu.entries if e.enabled]
        if entry.name in existing_names:
            return False, f"Entry '{entry.name}' already exists"

        menu.entries.append(entry)
        menu.entries.sort(key=lambda x: (x.order, x.name))

        return True, f"Entry '{entry.name}' added successfully"

    @safe_operation("iPXE entry removal", return_tuple=True)
    def remove_entry(self, menu: iPXEMenu, entry_name: str) -> Tuple[bool, str]:
        """Remove entry from menu"""
        original_count = len(menu.entries)
        menu.entries = [e for e in menu.entries if e.name != entry_name]

        if len(menu.entries) < original_count:
            # Update default entry if it was removed
            if menu.default_entry == entry_name:
                menu.default_entry = None
            return True, f"Entry '{entry_name}' removed successfully"
        else:
            return False, f"Entry '{entry_name}' not found"

    @safe_operation("iPXE menu validation and generation", return_tuple=True)
    def validate_and_generate(self, menu: iPXEMenu) -> Tuple[bool, str, str]:
        """Validate menu and generate iPXE script"""
        # Validate menu
        is_valid, errors = self.validator.validate_menu(menu)

        if not is_valid:
            error_msg = "Menu validation failed:\n" + "\n".join(f"• {error}" for error in errors)
            return False, error_msg, ""

        # Generate script
        try:
            script_content = self.generator.generate_ipxe_script(menu)
        except Exception as exc:
            return False, f"Menu generation failed: {exc}", ""
        success_msg = "✅ iPXE menu generated successfully"
        return True, success_msg, script_content

    def save_menu(self, menu: iPXEMenu) -> Tuple[bool, str]:
        """Validate, generate, and save iPXE menu using common utility"""
        is_valid, msg, script_content = self.validate_and_generate(menu)

        if not is_valid:
            return False, msg

        # Use common utility for safe file writing
        return safe_write_file(self.config_path, script_content)

    @safe_operation("iPXE menu loading")
    def load_menu_from_file(self) -> Tuple[bool, str, Optional[str]]:
        """Load existing iPXE menu from file"""
        if not self.config_path.exists():
            return False, f"Menu file not found: {self.config_path}", None

        with open(self.config_path, "r") as f:
            content = f.read()

        return True, f"Menu loaded from {self.config_path}", content

    @safe_operation("iPXE menu import", return_tuple=True)
    def import_menu_from_json(self, raw_json: str) -> Tuple[bool, str, Optional[iPXEMenu]]:
        """Load menu from JSON string using schema validation."""
        try:
            model = IpxeMenuModel.model_validate_json(raw_json)
        except ValidationError as exc:
            return False, f"JSON validation failed: {exc}", None

        menu = model_to_menu(model)
        return True, "Menu imported successfully", menu

    @safe_operation("iPXE menu generation from JSON", return_tuple=True)
    def generate_from_json(self, raw_json: str) -> Tuple[bool, str, str, List[str]]:
        """Import menu JSON, validate, lint, and generate script."""
        ok, msg, menu = self.import_menu_from_json(raw_json)
        if not ok or not menu:
            return False, msg, "", []

        is_valid, message, script_content = self.validate_and_generate(menu)
        warnings = self.validator.lint_menu(menu)

        if not is_valid:
            return False, message, "", warnings

        return True, message, script_content, warnings

    def get_template(
        self,
        template_name: str,
        server_ip: str = settings.pxe_server_ip,
        port: int = settings.http_port,
    ) -> Optional[iPXEMenu]:
        """Get pre-defined template"""
        templates = {
            "ubuntu": self.templates.get_ubuntu_template,
            "ubuntu_multi": self.templates.get_ubuntu_multi_template,
            "ubuntu_quick": self.templates.get_quick_ubuntu_template,
            "diagnostic": self.templates.get_diagnostic_template,
            "multi_os": self.templates.get_multi_os_template,
        }

        if template_name in templates:
            return templates[template_name](server_ip, port)

        return None

    def create_adaptive_ubuntu_menu(
        self,
        server_ip: str = settings.pxe_server_ip,
        port: int = settings.http_port,
        template_type: str = "multi",
    ) -> iPXEMenu:
        """Create Ubuntu menu based on available files"""

        # Detect available Ubuntu versions
        available_versions = self.detector.scan_available_versions()
        version_list = sorted(available_versions.keys(), reverse=True)  # Latest first

        if template_type == "quick":
            return self.templates.get_quick_ubuntu_template(server_ip, port)
        else:
            return self.templates.get_ubuntu_multi_template(server_ip, port, version_list)

    def get_version_status(self) -> Dict[str, Any]:
        """Get status of all Ubuntu versions and their capabilities"""
        versions = self.detector.scan_available_versions()

        status = {"versions_found": len(versions), "versions": {}}

        for version, capabilities in versions.items():
            boot_options = self.detector.get_boot_options_for_version(version, capabilities)

            status["versions"][version] = {
                "capabilities": capabilities,
                "boot_options": boot_options,
                "recommended": (
                    "netboot"
                    if "netboot" in boot_options
                    else boot_options[0] if boot_options else None
                ),
            }

        return status

    def export_menu_json(self, menu: iPXEMenu) -> str:
        """Export menu configuration to JSON using common utility"""
        model = menu_to_model(menu)
        return model.model_dump_json(indent=2)


# Convenience functions for backward compatibility and enhanced features
@safe_operation("Smart Ubuntu menu creation")
def create_smart_ubuntu_menu(
    server_ip: str = settings.pxe_server_ip,
    port: int = settings.http_port,
    template_type: str = "multi",
) -> str:
    """Create smart Ubuntu menu based on available files"""
    manager = iPXEManager()
    menu = manager.create_adaptive_ubuntu_menu(server_ip, port, template_type)
    return manager.generator.generate_ipxe_script(menu)


def get_ubuntu_status() -> Dict[str, Any]:
    """Get Ubuntu versions status"""
    detector = UbuntuVersionDetector()
    return detector.scan_available_versions()

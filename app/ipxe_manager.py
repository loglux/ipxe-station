"""
iPXE menu management for PXE Boot Station
Handles iPXE menu configuration generation, validation, and management
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse


@dataclass
class iPXEEntry:
    """Single iPXE menu entry"""
    name: str
    title: str
    kernel: str
    initrd: Optional[str] = None
    cmdline: str = ""
    description: str = ""
    enabled: bool = True
    order: int = 0
    entry_type: str = "boot"  # boot, menu, action, separator
    url: Optional[str] = None  # For HTTP boot entries

    def __post_init__(self):
        """Validate entry after initialization"""
        if not self.name:
            raise ValueError("Entry name cannot be empty")
        if not self.title:
            self.title = self.name
        # Sanitize name for iPXE compatibility
        self.name = re.sub(r'[^a-zA-Z0-9_-]', '_', self.name)


@dataclass
class iPXEMenu:
    """Complete iPXE menu configuration"""
    title: str = "PXE Boot Station"
    timeout: int = 30000  # milliseconds
    default_entry: Optional[str] = None
    entries: List[iPXEEntry] = field(default_factory=list)
    header_text: str = ""
    footer_text: str = ""
    server_ip: str = "localhost"
    http_port: int = 8000

    def __post_init__(self):
        """Sort entries by order after initialization"""
        self.entries.sort(key=lambda x: (x.order, x.name))


class iPXEValidator:
    """iPXE configuration validation utilities"""

    @staticmethod
    def validate_entry_name(name: str) -> Tuple[bool, str]:
        """Validate iPXE entry name"""
        if not name:
            return False, "Entry name cannot be empty"

        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            return False, "Entry name can only contain letters, numbers, underscores, and hyphens"

        if len(name) > 32:
            return False, "Entry name cannot exceed 32 characters"

        return True, "Valid entry name"

    @staticmethod
    def validate_kernel_path(kernel: str, server_ip: str = "localhost", port: int = 8000) -> Tuple[bool, str]:
        """Validate kernel path (file or URL)"""
        if not kernel:
            return False, "Kernel path cannot be empty"

        # Check if it's a URL
        if kernel.startswith(('http://', 'https://', 'tftp://')):
            try:
                parsed = urlparse(kernel)
                if not parsed.netloc:
                    return False, "Invalid URL format"
                return True, f"Valid URL: {kernel}"
            except Exception as e:
                return False, f"Invalid URL: {str(e)}"

        # Check if it's a local file path
        if kernel.startswith('/'):
            # Absolute path
            if Path(kernel).exists():
                return True, f"File exists: {kernel}"
            else:
                return False, f"File not found: {kernel}"
        else:
            # Relative path - assume it's served via HTTP
            full_url = f"http://{server_ip}:{port}/http/{kernel.lstrip('/')}"
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
    def validate_menu(menu: iPXEMenu) -> Tuple[bool, List[str]]:
        """Validate complete iPXE menu"""
        errors = []

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
        is_valid, msg = iPXEValidator.validate_timeout(menu.timeout)
        if not is_valid:
            errors.append(f"Timeout: {msg}")

        # Validate each entry
        for i, entry in enumerate(menu.entries):
            if not entry.enabled:
                continue

            # Validate entry name
            is_valid, msg = iPXEValidator.validate_entry_name(entry.name)
            if not is_valid:
                errors.append(f"Entry {i + 1} ({entry.name}): {msg}")

            # Validate kernel path for boot entries
            if entry.entry_type == "boot" and entry.kernel:
                is_valid, msg = iPXEValidator.validate_kernel_path(
                    entry.kernel, menu.server_ip, menu.http_port
                )
                if not is_valid:
                    errors.append(f"Entry {i + 1} ({entry.name}) kernel: {msg}")

        return len(errors) == 0, errors


class iPXEGenerator:
    """iPXE menu file generators"""

    @staticmethod
    def generate_ipxe_script(menu: iPXEMenu) -> str:
        """Generate iPXE script content"""
        script_lines = [
            "#!ipxe",
            "",
            "# iPXE Boot Menu",
            f"# Generated by PXE Boot Station at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        # Add header text if provided
        if menu.header_text:
            script_lines.extend([
                f"echo {menu.header_text}",
                "sleep 2",
                ""
            ])

        # Menu definition
        script_lines.extend([
            ":start",
            "menu",
            f"item --gap -- {menu.title}",
            "item --gap -- ────────────────────────────────────────",
        ])

        # Add menu entries
        for entry in menu.entries:
            if not entry.enabled:
                continue

            if entry.entry_type == "separator":
                script_lines.append("item --gap --")
            elif entry.entry_type == "boot":
                script_lines.append(f"item {entry.name} {entry.title}")
            elif entry.entry_type == "menu":
                script_lines.append(f"item {entry.name} {entry.title} -->")
            elif entry.entry_type == "action":
                script_lines.append(f"item {entry.name} {entry.title}")

        # Add standard menu items
        script_lines.extend([
            "item --gap --",
            "item shell Drop to iPXE shell",
            "item reboot Reboot computer",
            "item exit Exit to BIOS",
            ""
        ])

        # Set default and timeout - FIXED f-string issue
        if menu.default_entry:
            script_lines.append(
                f"choose --default {menu.default_entry} --timeout {menu.timeout} target && goto ${{target}}")
        else:
            script_lines.append(f"choose --timeout {menu.timeout} target && goto ${{target}}")

        script_lines.append("")

        # Generate boot sections for each entry
        for entry in menu.entries:
            if not entry.enabled or entry.entry_type != "boot":
                continue

            script_lines.extend([
                f":{entry.name}",
                f"echo Booting {entry.title}...",
            ])

            # Add description if provided
            if entry.description:
                script_lines.append(f"echo {entry.description}")

            # Determine kernel URL - FIXED to include /http/ path
            kernel_url = iPXEGenerator._resolve_kernel_url(entry.kernel, menu.server_ip, menu.http_port)
            script_lines.append(f"kernel {kernel_url} {entry.cmdline}".strip())

            # Add initrd if provided - FIXED to include /http/ path
            if entry.initrd:
                initrd_url = iPXEGenerator._resolve_kernel_url(entry.initrd, menu.server_ip, menu.http_port)
                script_lines.append(f"initrd {initrd_url}")

            script_lines.extend([
                "boot",
                "goto start",
                ""
            ])

        # Standard menu actions
        script_lines.extend([
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
            "goto start"
        ])

        # Add footer text if provided
        if menu.footer_text:
            script_lines.extend([
                "",
                f"echo {menu.footer_text}",
            ])

        return "\n".join(script_lines)

    @staticmethod
    def _resolve_kernel_url(path: str, server_ip: str, port: int) -> str:
        """Resolve kernel path to full URL - FIXED to include /http/ path"""
        if path.startswith(('http://', 'https://', 'tftp://')):
            return path
        elif path.startswith('/'):
            # Absolute path - convert to HTTP URL with /http/ prefix
            return f"http://{server_ip}:{port}/http{path}"
        else:
            # Relative path - convert to HTTP URL with /http/ prefix
            return f"http://{server_ip}:{port}/http/{path.lstrip('/')}"

    @staticmethod
    def generate_grub_config(menu: iPXEMenu) -> str:
        """Generate GRUB configuration (for comparison/fallback)"""
        grub_lines = [
            "# GRUB Configuration",
            f"# Generated by PXE Boot Station at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"set timeout={menu.timeout // 1000}",
            f"set default=0",
            ""
        ]

        boot_entries = [entry for entry in menu.entries if entry.enabled and entry.entry_type == "boot"]

        for i, entry in enumerate(boot_entries):
            grub_lines.extend([
                f"menuentry '{entry.title}' {{",
                f"    echo 'Loading {entry.title}...'",
                f"    linux {entry.kernel} {entry.cmdline}".strip(),
            ])

            if entry.initrd:
                grub_lines.append(f"    initrd {entry.initrd}")

            grub_lines.extend([
                "}",
                ""
            ])

        return "\n".join(grub_lines)


class iPXETemplateManager:
    """Pre-defined iPXE menu templates"""

    @staticmethod
    def get_ubuntu_template(server_ip: str = "localhost", port: int = 8000) -> iPXEMenu:
        """Ubuntu installation template"""
        entries = [
            iPXEEntry(
                name="ubuntu_install",
                title="Install Ubuntu 22.04 LTS",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                cmdline="ip=dhcp url=http://{server_ip}:{port}/http/ubuntu/ubuntu-22.04-live-server-amd64.iso autoinstall ds=nocloud-net;s=http://{server_ip}:{port}/http/cloud-init/",
                description="Automated Ubuntu Server installation",
                order=1
            ),
            iPXEEntry(
                name="ubuntu_live",
                title="Ubuntu 22.04 Live Session",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                cmdline="ip=dhcp boot=casper netboot=nfs nfsroot={server_ip}:/srv/nfs/ubuntu",
                description="Live Ubuntu session without installation",
                order=2
            ),
            iPXEEntry(
                name="ubuntu_rescue",
                title="Ubuntu Rescue Mode",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                cmdline="ip=dhcp rescue/enable=true",
                description="Ubuntu rescue and recovery mode",
                order=3
            )
        ]

        # Format cmdline with actual server IP and port
        for entry in entries:
            entry.cmdline = entry.cmdline.format(server_ip=server_ip, port=port)

        return iPXEMenu(
            title="Ubuntu PXE Boot Menu",
            timeout=30000,
            default_entry="ubuntu_install",
            entries=entries,
            server_ip=server_ip,
            http_port=port,
            header_text="Welcome to Ubuntu PXE Boot Station",
            footer_text="Use arrow keys to navigate, Enter to select"
        )

    @staticmethod
    def get_diagnostic_template(server_ip: str = "localhost", port: int = 8000) -> iPXEMenu:
        """System diagnostic tools template"""
        entries = [
            iPXEEntry(
                name="memtest",
                title="Memory Test (Memtest86+)",
                kernel="tools/memtest86+.bin",
                description="Test system memory for errors",
                order=1
            ),
            iPXEEntry(
                name="hdparm",
                title="Hard Drive Diagnostics",
                kernel="tools/hdparm.img",
                description="Hard drive testing and diagnostics",
                order=2
            ),
            iPXEEntry(
                name="dban",
                title="DBAN - Disk Wipe Utility",
                kernel="tools/dban.img",
                description="Secure disk wiping utility",
                order=3
            )
        ]

        return iPXEMenu(
            title="System Diagnostic Tools",
            timeout=60000,
            entries=entries,
            server_ip=server_ip,
            http_port=port,
            header_text="System Diagnostic and Repair Tools",
            footer_text="WARNING: Some tools may modify or erase data!"
        )

    @staticmethod
    def get_multi_os_template(server_ip: str = "localhost", port: int = 8000) -> iPXEMenu:
        """Multi-OS boot template"""
        entries = [
            iPXEEntry(
                name="separator1",
                title="Linux Distributions",
                entry_type="separator",
                order=1
            ),
            iPXEEntry(
                name="ubuntu",
                title="Ubuntu 22.04 LTS",
                kernel="ubuntu/vmlinuz",
                initrd="ubuntu/initrd",
                cmdline="ip=dhcp",
                order=2
            ),
            iPXEEntry(
                name="centos",
                title="CentOS Stream 9",
                kernel="centos/vmlinuz",
                initrd="centos/initrd.img",
                cmdline="ip=dhcp inst.repo=http://{server_ip}:{port}/http/centos/",
                order=3
            ),
            iPXEEntry(
                name="separator2",
                title="Utilities",
                entry_type="separator",
                order=4
            ),
            iPXEEntry(
                name="clonezilla",
                title="Clonezilla Live",
                kernel="clonezilla/vmlinuz",
                initrd="clonezilla/initrd.img",
                cmdline="boot=live config noswap nolocales edd=on ocs_live_run=\"ocs-live-general\"",
                order=5
            ),
            iPXEEntry(
                name="gparted",
                title="GParted Live",
                kernel="gparted/vmlinuz",
                initrd="gparted/initrd.img",
                cmdline="boot=live config union=overlay username=user noswap noeject ip= vga=788",
                order=6
            )
        ]

        # Format cmdline with actual server IP and port
        for entry in entries:
            if entry.cmdline:
                entry.cmdline = entry.cmdline.format(server_ip=server_ip, port=port)

        return iPXEMenu(
            title="Multi-OS PXE Boot Menu",
            timeout=45000,
            default_entry="ubuntu",
            entries=entries,
            server_ip=server_ip,
            http_port=port,
            header_text="Multiple Operating Systems and Tools",
            footer_text="Select an option or wait for default selection"
        )


class iPXEManager:
    """Main iPXE menu management class"""

    def __init__(self, config_path: str = "/srv/ipxe/boot.ipxe"):
        self.config_path = Path(config_path)
        self.validator = iPXEValidator()
        self.generator = iPXEGenerator()
        self.templates = iPXETemplateManager()

    def create_menu(self, title: str = "PXE Boot Menu", server_ip: str = "localhost",
                    port: int = 8000) -> iPXEMenu:
        """Create new empty iPXE menu"""
        return iPXEMenu(
            title=title,
            server_ip=server_ip,
            http_port=port
        )

    def add_entry(self, menu: iPXEMenu, entry: iPXEEntry) -> Tuple[bool, str]:
        """Add entry to menu"""
        # Validate entry
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
            success_msg = "✅ iPXE menu generated successfully"
            return True, success_msg, script_content
        except Exception as e:
            return False, f"Script generation failed: {str(e)}", ""

    def save_menu(self, menu: iPXEMenu) -> Tuple[bool, str]:
        """Validate, generate, and save iPXE menu"""
        is_valid, msg, script_content = self.validate_and_generate(menu)

        if not is_valid:
            return False, msg

        try:
            # Create directory if it doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Save script
            with open(self.config_path, 'w') as f:
                f.write(script_content)

            return True, f"✅ iPXE menu saved to {self.config_path}"
        except Exception as e:
            return False, f"❌ Failed to save menu: {str(e)}"

    def load_menu_from_file(self) -> Tuple[bool, str, Optional[str]]:
        """Load existing iPXE menu from file"""
        try:
            if not self.config_path.exists():
                return False, f"Menu file not found: {self.config_path}", None

            with open(self.config_path, 'r') as f:
                content = f.read()

            return True, f"Menu loaded from {self.config_path}", content
        except Exception as e:
            return False, f"Failed to load menu: {str(e)}", None

    def get_template(self, template_name: str, server_ip: str = "localhost",
                     port: int = 8000) -> Optional[iPXEMenu]:
        """Get pre-defined template"""
        templates = {
            "ubuntu": self.templates.get_ubuntu_template,
            "diagnostic": self.templates.get_diagnostic_template,
            "multi_os": self.templates.get_multi_os_template
        }

        if template_name in templates:
            return templates[template_name](server_ip, port)

        return None

    def export_menu_json(self, menu: iPXEMenu) -> str:
        """Export menu configuration to JSON"""
        menu_dict = {
            "title": menu.title,
            "timeout": menu.timeout,
            "default_entry": menu.default_entry,
            "server_ip": menu.server_ip,
            "http_port": menu.http_port,
            "header_text": menu.header_text,
            "footer_text": menu.footer_text,
            "entries": [
                {
                    "name": entry.name,
                    "title": entry.title,
                    "kernel": entry.kernel,
                    "initrd": entry.initrd,
                    "cmdline": entry.cmdline,
                    "description": entry.description,
                    "enabled": entry.enabled,
                    "order": entry.order,
                    "entry_type": entry.entry_type,
                    "url": entry.url
                }
                for entry in menu.entries
            ]
        }

        return json.dumps(menu_dict, indent=2)
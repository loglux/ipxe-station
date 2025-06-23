"""
Gradio Web UI for PXE Boot Station - Multi-version Ubuntu Support
Refactored to use modular architecture with enhanced Ubuntu management
REFACTORED: Eliminated repetitions with helper functions and decorators
"""

import gradio as gr
import json
import os
from typing import Dict, List, Tuple, Optional, Any

# Import our modular components with error handling
try:
    from tests import SystemTester
    from tests import test_http_endpoints as legacy_test_http_endpoints
except ImportError:
    SystemTester = None
    legacy_test_http_endpoints = None

try:
    from dhcp_config import DHCPConfigManager, DHCPConfig, create_simple_config
except ImportError:
    DHCPConfigManager = None
    DHCPConfig = None
    create_simple_config = None

try:
    from ipxe_manager import iPXEManager, iPXEMenu, iPXEEntry, iPXETemplateManager
except ImportError:
    iPXEManager = None
    iPXEMenu = None
    iPXEEntry = None
    iPXETemplateManager = None

try:
    from system_status import SystemStatusManager, get_system_status
except ImportError:
    SystemStatusManager = None
    get_system_status = None

try:
    from ubuntu_downloader import UbuntuDownloader
except ImportError:
    UbuntuDownloader = None

try:
    from iso_manager import ISOManager
except ImportError:
    ISOManager = None

try:
    from file_utils import FileManager
except ImportError:
    FileManager = None


# === UI HELPER FUNCTIONS ===
def safe_method(module_attr=None, error_prefix="Operation"):
    """
    Decorator for safe method calls with unified error handling.

    Args:
        module_attr: Name of the module attribute to check (e.g., 'ubuntu_downloader')
        error_prefix: Prefix for error messages (e.g., 'Ubuntu download')

    Usage:
        @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu download')
        def download_ubuntu_files(self, version: str):
            return self.ubuntu_downloader.download_all_files(version)
    """

    def decorator(func):
        def wrapper(self, *args, **kwargs):
            try:
                # Check if required module is available
                if module_attr and not getattr(self, module_attr, None):
                    return f"❌ {error_prefix} module not available"

                # Execute the actual method
                return func(self, *args, **kwargs)

            except Exception as e:
                return f"❌ {error_prefix} failed: {str(e)}"

        # Preserve original function metadata
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


def _create_status_textbox(label="Status", lines=10, initial_value="", max_lines=None, show_label=True, **kwargs):
    """
    Create standardized status textbox component.

    Args:
        label: Textbox label
        lines: Number of visible lines
        initial_value: Initial text content
        max_lines: Maximum expandable lines
        show_label: Whether to show the label
        **kwargs: Additional Gradio textbox parameters

    Returns:
        gr.Textbox: Configured textbox component
    """
    return gr.Textbox(
        label=label,
        value=initial_value,
        lines=lines,
        max_lines=max_lines,
        interactive=False,
        show_label=show_label,
        **kwargs
    )


def _create_action_buttons(*button_configs):
    """
    Create a row of action buttons with consistent styling.

    Args:
        *button_configs: Tuples of (text, variant, icon) for each button

    Usage:
        download_btn, check_btn = _create_action_buttons(
            ("Download", "primary", "⬇️"),
            ("Check All", "secondary", "🔍")
        )

    Returns:
        tuple: Button components
    """
    buttons = []
    for config in button_configs:
        if len(config) == 3:
            text, variant, icon = config
            button_text = f"{icon} {text}" if icon else text
        elif len(config) == 2:
            text, variant = config
            button_text = text
        else:
            text = config[0]
            variant = "secondary"
            button_text = text

        btn = gr.Button(button_text, variant=variant)
        buttons.append(btn)

    return tuple(buttons) if len(buttons) > 1 else buttons[0]


class PXEBootStationUI:
    """Main UI controller class with multi-version Ubuntu support"""

    def __init__(self):
        # Initialize components with fallbacks
        self.system_tester = SystemTester() if SystemTester else None
        self.dhcp_manager = DHCPConfigManager() if DHCPConfigManager else None
        self.ipxe_manager = iPXEManager() if iPXEManager else None
        self.status_manager = SystemStatusManager() if SystemStatusManager else None
        self.ubuntu_downloader = UbuntuDownloader() if UbuntuDownloader else None
        self.file_manager = FileManager() if FileManager else None
        self.ipxe_templates = iPXETemplateManager() if iPXETemplateManager else None
        self.iso_manager = ISOManager() if ISOManager else None

    # ===========================
    # HELPER METHODS FOR DROPDOWNS
    # ===========================

    def _create_refresh_dropdown(self, get_func, empty_msg="No items found", error_msg="Error"):
        """
        Universal dropdown refresh method.

        Args:
            get_func: Function to get choices list
            empty_msg: Message when no items found
            error_msg: Message on error

        Returns:
            gr.update: Dropdown update configuration
        """
        try:
            items = get_func()
            value = items[0] if items and items[0] != empty_msg else empty_msg
            return gr.update(choices=items, value=value)
        except Exception:
            return gr.update(choices=[error_msg], value=error_msg)

    # =========================
    # SYSTEM STATUS TAB
    # =========================

    @safe_method(module_attr='status_manager', error_prefix='System status')
    def get_system_status_display(self) -> str:
        """Get formatted system status for display"""
        status = self.status_manager.get_complete_status()

        output = []
        output.append("🖥️ **SYSTEM STATUS**")
        output.append("=" * 50)

        # System info
        sys_info = status['system']
        output.append(f"🏠 **Hostname:** {sys_info['hostname']}")
        output.append(f"💻 **Platform:** {sys_info['platform']} ({sys_info['architecture']})")
        output.append(f"⚡ **CPU:** {sys_info['cpu_count']} cores, {sys_info['cpu_percent']:.1f}% used")
        output.append(
            f"🧠 **Memory:** {sys_info['memory_available_gb']:.1f}GB free / {sys_info['memory_total_gb']:.1f}GB total ({sys_info['memory_percent']:.1f}% used)")
        output.append(f"⏰ **Uptime:** {sys_info['uptime']}")
        output.append("")

        # Services status
        output.append("🔧 **SERVICES STATUS**")
        output.append("-" * 30)
        for name, service in status['services'].items():
            status_icon = {
                'running': '✅',
                'stopped': '❌',
                'error': '🔥',
                'unknown': '❓'
            }.get(service['status'], '❓')

            output.append(f"{status_icon} **{service['description']}**")
            output.append(f"   Status: {service['status'].upper()}")
            if service['pid']:
                output.append(f"   PID: {service['pid']}")
            if service['port']:
                output.append(f"   Port: {service['port']}/{service['protocol'].upper()}")
            if service['uptime']:
                output.append(f"   Uptime: {service['uptime']}")
            if service['error_message']:
                output.append(f"   Info: {service['error_message']}")
            output.append("")

        # Disk usage
        output.append("💾 **DISK USAGE**")
        output.append("-" * 20)
        for disk in status['disk_usage']:
            output.append(f"📁 **{disk['path']}**")
            output.append(f"   Total: {disk['total_gb']:.1f}GB")
            output.append(f"   Used: {disk['used_gb']:.1f}GB ({disk['percent']:.1f}%)")
            output.append(f"   Free: {disk['free_gb']:.1f}GB")
            output.append("")

        # PXE files status
        output.append("📋 **PXE FILES STATUS**")
        output.append("-" * 25)
        for name, file_info in status['pxe_files'].items():
            status_icon = '✅' if file_info['exists'] else '❌'
            output.append(f"{status_icon} **{name}**")
            output.append(f"   Path: {file_info['path']}")
            if file_info['exists']:
                output.append(f"   Size: {file_info['size_human']}")
                if file_info['modified']:
                    output.append(f"   Modified: {file_info['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                output.append(f"   Status: Missing")
            output.append("")

        # Health score and recommendations
        output.append("🏥 **SYSTEM HEALTH**")
        output.append("-" * 20)
        health_score = status['health_score']
        health_emoji = '🟢' if health_score >= 80 else '🟡' if health_score >= 60 else '🔴'
        output.append(f"{health_emoji} **Overall Health Score: {health_score}/100**")
        output.append("")

        output.append("💡 **RECOMMENDATIONS**")
        output.append("-" * 20)
        for rec in status['recommendations']:
            output.append(f"• {rec}")

        return "\n".join(output)

    @safe_method(module_attr='status_manager', error_prefix='System status refresh')
    def refresh_system_status(self) -> str:
        """Refresh system status"""
        return self.get_system_status_display()

    @safe_method(module_attr='status_manager', error_prefix='System status export')
    def export_system_status(self) -> str:
        """Export system status as JSON"""
        return self.status_manager.export_status_json()

    # =========================
    # TESTING TAB
    # =========================

    @safe_method(module_attr='system_tester', error_prefix='System testing')
    def run_full_system_test(self) -> str:
        """Run comprehensive system test"""
        return self.system_tester.run_full_system_test()

    @safe_method(module_attr='system_tester', error_prefix='TFTP test')
    def test_tftp_connection(self, host: str = "localhost", port: int = 69,
                             filename: str = "undionly.kpxe", timeout: int = 5) -> str:
        """Test TFTP connection with custom parameters"""
        return self.system_tester.tftp_tester.test_tftp_connection(host, port, filename, timeout)

    @safe_method(module_attr='system_tester', error_prefix='HTTP test')
    def test_http_endpoint(self, url: str = "http://localhost:8000/status", timeout: int = 5) -> str:
        """Test HTTP endpoint"""
        return self.system_tester.http_tester.test_endpoint(url, timeout)

    @safe_method(module_attr='system_tester', error_prefix='File check')
    def check_file_exists(self, filepath: str) -> str:
        """Check if file exists"""
        return self.system_tester.file_checker.check_file_exists(filepath)

    @safe_method(error_prefix='Legacy HTTP test')
    def run_legacy_http_test(self) -> str:
        """Run legacy HTTP test"""
        if not legacy_test_http_endpoints:
            return "❌ Legacy test function not available"
        return legacy_test_http_endpoints()

    # =========================
    # DHCP CONFIGURATION TAB
    # =========================

    @safe_method(module_attr='dhcp_manager', error_prefix='DHCP configuration')
    def generate_dhcp_config(self, server_ip: str, subnet: str, netmask: str,
                             router_ip: str, dns_servers: str, config_type: str,
                             lease_time: int = 86400, domain_name: str = "") -> Tuple[str, str]:
        """Generate DHCP configuration"""
        # Parse DNS servers
        dns_list = [dns.strip() for dns in dns_servers.split(",") if dns.strip()]

        # Create config object
        config = self.dhcp_manager.create_config(
            server_ip=server_ip,
            subnet=subnet,
            netmask=netmask,
            router_ip=router_ip,
            dns_servers=dns_list,
            lease_time=lease_time,
            domain_name=domain_name if domain_name else None
        )

        # Validate and generate
        is_valid, message, config_content = self.dhcp_manager.validate_and_generate(config, config_type)
        return message, config_content if is_valid else ""

    @safe_method(module_attr='dhcp_manager', error_prefix='DHCP configuration save')
    def save_dhcp_config(self, config_content: str, config_type: str) -> str:
        """Save DHCP configuration to file"""
        if not config_content:
            return "❌ No configuration content to save"

        # Cross-platform file paths
        if os.name == 'nt':  # Windows
            base_path = "C:/srv/dhcp"
        else:  # Unix-like
            base_path = "/srv/dhcp"

        filename_map = {
            "isc": f"{base_path}/dhcpd.conf",
            "dnsmasq": f"{base_path}/dnsmasq.conf",
            "mikrotik": f"{base_path}/mikrotik_commands.txt"
        }

        filepath = filename_map.get(config_type.lower(), f"{base_path}/{config_type}.conf")
        is_saved, message = self.dhcp_manager.save_config(config_content, filepath)
        return message

    @safe_method(module_attr='dhcp_manager', error_prefix='Simple DHCP configuration')
    def create_simple_dhcp_config(self, server_ip: str, network_cidr: str) -> Tuple[str, str]:
        """Create simple DHCP configuration from CIDR"""
        if not create_simple_config:
            return "❌ Simple config function not available", ""

        config = create_simple_config(server_ip, network_cidr)
        is_valid, message, config_content = self.dhcp_manager.validate_and_generate(config, "isc")
        return message, config_content if is_valid else ""

    # =========================
    # iPXE MENU TAB
    # =========================

    @safe_method(module_attr='ipxe_manager', error_prefix='iPXE template creation')
    def create_ipxe_menu_from_template(self, template_name: str, server_ip: str = "localhost",
                                       port: int = 8000) -> Tuple[str, str]:
        """Create iPXE menu from template with auto-detection of Ubuntu versions"""
        menu = self.ipxe_manager.get_template(template_name, server_ip, port)
        if not menu:
            return f"❌ Template '{template_name}' not found", ""

        # If template is Ubuntu-related, add all installed versions
        if template_name == "ubuntu" and self.ubuntu_downloader:
            installed_versions = self.ubuntu_downloader.get_installed_versions()
            if installed_versions:
                # Clear existing Ubuntu entries and add all installed versions
                menu.entries = [e for e in menu.entries if "ubuntu" not in e.name.lower()]

                for i, version in enumerate(installed_versions):
                    entry = iPXEEntry(
                        name=f"ubuntu_{version.replace('.', '_')}",
                        title=f"Ubuntu {version} LTS",
                        kernel=f"ubuntu-{version}/vmlinuz",
                        initrd=f"ubuntu-{version}/initrd",
                        cmdline=f"ip=dhcp url=http://{server_ip}:{port}/http/ubuntu-{version}/preseed.cfg",
                        description=f"Ubuntu {version} automated installation",
                        order=i + 1
                    )
                    menu.entries.append(entry)

                menu.default_entry = f"ubuntu_{installed_versions[0].replace('.', '_')}"

        is_valid, message, script_content = self.ipxe_manager.validate_and_generate(menu)
        return message, script_content if is_valid else ""

    @safe_method(error_prefix='iPXE menu save')
    def save_ipxe_menu(self, script_content: str) -> str:
        """Save iPXE menu script"""
        if not script_content:
            return "❌ No script content to save"

        # Cross-platform file path
        if os.name == 'nt':  # Windows
            filepath = "C:/srv/ipxe/boot.ipxe"
        else:  # Unix-like
            filepath = "/srv/ipxe/boot.ipxe"

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Save to file
        with open(filepath, "w") as f:
            f.write(script_content)

        return f"✅ iPXE menu saved to {filepath}"

    def add_custom_ipxe_entry(self, menu_script: str, entry_name: str, entry_title: str,
                              kernel_path: str, initrd_path: str = "", cmdline: str = "",
                              description: str = "") -> str:
        """Add custom entry to iPXE menu"""
        if not menu_script:
            return "❌ No menu script provided"

        # This is a simplified version - in practice you'd parse the existing script
        # and add the new entry properly
        new_entry_section = f"""
:{entry_name}
echo Booting {entry_title}...
"""
        if description:
            new_entry_section += f"echo {description}\n"

        new_entry_section += f"kernel {kernel_path} {cmdline}\n"

        if initrd_path:
            new_entry_section += f"initrd {initrd_path}\n"

        new_entry_section += """boot
goto start

"""

        # Add menu item (simplified)
        menu_item = f"item {entry_name} {entry_title}\n"

        # Insert into script (this is a basic implementation)
        if "item --gap --" in menu_script:
            updated_script = menu_script.replace(
                "item --gap --\nitem shell",
                f"item --gap --\n{menu_item}item shell"
            )
            updated_script += new_entry_section
            return updated_script
        else:
            return menu_script + new_entry_section

    def validate_ipxe_script(self, script_content: str) -> str:
        """Validate iPXE script"""
        if not script_content:
            return "❌ No script content to validate"

        # Basic validation
        if not script_content.startswith("#!ipxe"):
            return "⚠️ Script should start with '#!ipxe'"

        if ":start" not in script_content:
            return "⚠️ Script should contain ':start' label"

        if "choose" not in script_content:
            return "⚠️ Script should contain 'choose' command"

        return "✅ iPXE script validation passed"

    # =========================
    # UBUNTU DOWNLOAD TAB - ENHANCED
    # =========================

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu download')
    def download_ubuntu_files(self, version: str = "22.04", progress=gr.Progress()) -> str:
        """Download Ubuntu files with progress tracking"""

        def progress_callback(current: int, total: int, filename: str):
            if total > 0:
                percent = (current / total) * 100
                progress(percent / 100, desc=f"Downloading {filename}")

        result = self.ubuntu_downloader.download_all_files(
            version=version,
            progress_callback=progress_callback
        )
        return result

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu files check')
    def check_ubuntu_files(self) -> str:
        """Check all Ubuntu files status"""
        return self.ubuntu_downloader.check_files_status()

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu version check')
    def check_specific_ubuntu_version(self, version: str) -> str:
        """Check files for specific Ubuntu version"""
        if not version or version in ["No versions installed", "Error"]:
            return "❌ Please select a valid version to check"
        return self.ubuntu_downloader.check_files_status(version)

    def get_installed_ubuntu_versions(self) -> list:
        """Get list of installed Ubuntu versions for dropdown"""
        if not self.ubuntu_downloader:
            return ["No versions found"]

        installed = self.ubuntu_downloader.get_installed_versions()
        return installed if installed else ["No versions installed"]

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu version deletion')
    def delete_ubuntu_version(self, version: str) -> str:
        """Delete specific Ubuntu version"""
        if not version or version in ["No versions installed", "Error"]:
            return "❌ Please select a valid version to delete"
        return self.ubuntu_downloader.delete_version(version)

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu versions deletion')
    def delete_all_ubuntu_versions(self) -> str:
        """Delete all Ubuntu versions"""
        return self.ubuntu_downloader.delete_all_versions()

    def refresh_ubuntu_versions_dropdown(self) -> dict:
        """Refresh the installed versions dropdown"""
        return self._create_refresh_dropdown(
            self.get_installed_ubuntu_versions,
            empty_msg="No versions installed"
        )

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu summary')
    def get_ubuntu_summary(self) -> str:
        """Get Ubuntu installations summary"""
        installed = self.ubuntu_downloader.get_installed_versions()
        supported = list(self.ubuntu_downloader.get_supported_versions().keys())

        summary = []
        summary.append("📊 **Ubuntu Versions Overview**")
        summary.append(f"📁 Installed: {len(installed)} versions")
        summary.append(f"🔢 Available: {len(supported)} versions")

        if installed:
            summary.append(f"✅ Installed versions: {', '.join(installed)}")
        else:
            summary.append("ℹ️ No versions installed yet")

        summary.append(f"📥 Available to download: {', '.join(supported)}")
        return "\n".join(summary)

    @safe_method(module_attr='ipxe_manager', error_prefix='Smart Ubuntu menu creation')
    def create_smart_ubuntu_menu(self, template_type: str = "multi", server_ip: str = "localhost",
                                 port: int = 8000) -> Tuple[str, str]:
        """Create smart Ubuntu menu with multiple boot options"""
        # Create adaptive menu based on available files
        menu = self.ipxe_manager.create_adaptive_ubuntu_menu(server_ip, port, template_type)

        # Generate script
        is_valid, message, script_content = self.ipxe_manager.validate_and_generate(menu)

        if not is_valid:
            return message, ""

        # Get status info
        version_status = self.ipxe_manager.get_version_status()

        status_msg = f"✅ Smart Ubuntu menu created!\n"
        status_msg += f"📊 Found {version_status['versions_found']} Ubuntu versions\n\n"

        for version, info in version_status['versions'].items():
            status_msg += f"🐧 **Ubuntu {version}**:\n"
            status_msg += f"   • Boot options: {', '.join(info['boot_options'])}\n"
            status_msg += f"   • Recommended: {info['recommended']}\n"

            caps = info['capabilities']
            if caps['iso']:
                status_msg += f"   • ✅ Live boot available (ISO found)\n"
            else:
                status_msg += f"   • ❌ Live boot unavailable (ISO missing)\n"

            if caps['preseed']:
                status_msg += f"   • ✅ Auto-install available (preseed found)\n"
            else:
                status_msg += f"   • ❌ Auto-install unavailable (preseed missing)\n"
            status_msg += "\n"

        return status_msg, script_content

    @safe_method(module_attr='ipxe_manager', error_prefix='Ubuntu capabilities analysis')
    def get_ubuntu_capabilities_status(self) -> str:
        """Get detailed Ubuntu capabilities status"""
        versions = self.ipxe_manager.detector.scan_available_versions()

        if not versions:
            return "❌ No Ubuntu versions found in /srv/http/"

        status = "🐧 **Ubuntu Versions Analysis**\n"
        status += "=" * 50 + "\n\n"

        for version, capabilities in versions.items():
            status += f"📦 **Ubuntu {version} LTS**\n"
            status += f"   📁 Path: /srv/http/ubuntu-{version}/\n"

            # File status
            file_status = []
            if capabilities['kernel']:
                file_status.append("✅ Kernel")
            else:
                file_status.append("❌ Kernel")

            if capabilities['initrd']:
                file_status.append("✅ Initrd")
            else:
                file_status.append("❌ Initrd")

            if capabilities['iso']:
                file_status.append("✅ ISO")
            else:
                file_status.append("❌ ISO")

            if capabilities['preseed']:
                file_status.append("✅ Preseed")
            else:
                file_status.append("❌ Preseed")

            status += f"   📋 Files: {' | '.join(file_status)}\n"

            # Boot options
            boot_options = self.ipxe_manager.detector.get_boot_options_for_version(version, capabilities)

            status += f"   🚀 **Available Boot Modes:**\n"
            for option in boot_options:
                mode_info = {
                    "netboot": "🌐 Network Install (requires internet)",
                    "live": "💿 Live Boot (requires ISO)",
                    "rescue": "🔧 Rescue Mode",
                    "preseed": "⚡ Auto Install (requires preseed)"
                }
                status += f"      • {mode_info.get(option, option)}\n"

            if not boot_options:
                status += f"      ❌ No boot options available (missing kernel/initrd)\n"

            status += "\n"

        # Summary recommendations
        status += "💡 **Recommendations:**\n"

        working_versions = [v for v, c in versions.items() if c['kernel'] and c['initrd']]
        if working_versions:
            status += f"✅ Working versions: {', '.join(working_versions)}\n"

        iso_missing = [v for v, c in versions.items() if c['kernel'] and c['initrd'] and not c['iso']]
        if iso_missing:
            status += f"💿 To enable Live Boot, download ISO files for: {', '.join(iso_missing)}\n"

        preseed_missing = [v for v, c in versions.items() if c['kernel'] and c['initrd'] and not c['preseed']]
        if preseed_missing:
            status += f"⚡ To enable Auto Install, add preseed.cfg for: {', '.join(preseed_missing)}\n"

        return status

    @safe_method(module_attr='ipxe_manager', error_prefix='ISO download suggestions')
    def create_ubuntu_iso_download_suggestions(self) -> str:
        """Generate suggestions for downloading missing ISO files"""
        versions = self.ipxe_manager.detector.scan_available_versions()

        suggestions = "💿 **Ubuntu ISO Download Suggestions**\n"
        suggestions += "=" * 50 + "\n\n"

        iso_needed = []
        for version, capabilities in versions.items():
            if capabilities['kernel'] and capabilities['initrd'] and not capabilities['iso']:
                iso_needed.append(version)

        if not iso_needed:
            suggestions += "✅ All available Ubuntu versions have ISO files!\n"
            return suggestions

        suggestions += "📥 **Missing ISO files for:**\n\n"

        for version in iso_needed:
            suggestions += f"🐧 **Ubuntu {version} LTS**\n"

            # ISO download URLs
            if version == "24.04":
                iso_url = "https://releases.ubuntu.com/noble/ubuntu-24.04.2-live-server-amd64.iso"
            elif version == "22.04":
                iso_url = "https://releases.ubuntu.com/jammy/ubuntu-22.04.5-live-server-amd64.iso"
            elif version == "20.04":
                iso_url = "https://releases.ubuntu.com/focal/ubuntu-20.04.6-live-server-amd64.iso"
            else:
                iso_url = f"https://releases.ubuntu.com/ubuntu-{version}-live-server-amd64.iso"

            target_path = f"/srv/http/ubuntu-{version}/ubuntu-{version}-live-server-amd64.iso"

            suggestions += f"   📎 URL: {iso_url}\n"
            suggestions += f"   📁 Target: {target_path}\n"
            suggestions += f"   📦 Size: ~2.5GB\n"
            suggestions += f"   ⚡ Command: `wget {iso_url} -O {target_path}`\n\n"

        suggestions += "💡 **Benefits of having ISO files:**\n"
        suggestions += "   • 💿 Enable Live Boot mode (test without installing)\n"
        suggestions += "   • 🚀 Faster installation (no internet download)\n"
        suggestions += "   • 🔒 Offline installation capability\n"
        suggestions += "   • 🎯 Complete Ubuntu experience\n"

        return suggestions

    # =========================
    # ISO MANAGEMENT TAB
    # =========================

    @safe_method(module_attr='iso_manager', error_prefix='ISO download')
    def download_iso_from_url(self, url: str, folder_name: str, display_name: str,
                              category: str = "custom", extract_files: bool = False,
                              iso_retention: str = "keep", progress=gr.Progress()) -> str:
        """Download ISO from URL with progress tracking and optional extraction"""

        def progress_callback(current: int, total: int, filename: str):
            if total > 0:
                percent = (current / total) * 100
                progress(percent / 100, desc=f"Downloading {filename}")

        result = self.iso_manager.download_iso_from_url(
            url=url,
            folder_name=folder_name,
            display_name=display_name,
            category=category,
            extract_files=extract_files,
            iso_retention=iso_retention,
            progress_callback=progress_callback
        )
        return result

    @safe_method(module_attr='iso_manager', error_prefix='ISO upload')
    def upload_iso_file(self, file_obj, folder_name: str, display_name: str,
                        category: str = "custom", extract_files: bool = False,
                        iso_retention: str = "keep") -> str:
        """Upload ISO file from local system with optional extraction"""
        if not file_obj:
            return "❌ No file selected for upload"

        result = self.iso_manager.upload_iso_file(
            file_obj=file_obj,
            folder_name=folder_name,
            display_name=display_name,
            category=category,
            extract_files=extract_files,
            iso_retention=iso_retention
        )
        return result

    def get_iso_retention_options(self) -> list:
        """Get ISO retention options for dropdown"""
        if not self.iso_manager:
            return ["keep"]

        options = self.iso_manager.get_iso_retention_options()
        return list(options.keys())

    def get_iso_retention_labels(self) -> dict:
        """Get ISO retention options with labels"""
        if not self.iso_manager:
            return {"keep": "Keep in same folder"}
        return self.iso_manager.get_iso_retention_options()

    def get_iso_folder_names(self) -> List[str]:
        """Get list of existing ISO folder names for dropdowns"""
        if not self.iso_manager:
            return ["No ISOs found"]

        isos = self.iso_manager.list_existing_isos()
        if not isos:
            return ["No ISOs found"]

        folders = [iso["folder_name"] for iso in isos]
        return sorted(folders)

    def refresh_iso_list(self) -> dict:
        """Refresh ISO dropdown list"""
        return self._create_refresh_dropdown(
            self.get_iso_folder_names,
            empty_msg="No ISOs found"
        )

    @safe_method(module_attr='iso_manager', error_prefix='ISO status check')
    def get_iso_status(self, folder_name: str = None) -> str:
        """Get detailed status of ISOs"""
        if folder_name and folder_name != "No ISOs found":
            return self.iso_manager.get_iso_status(folder_name)
        elif folder_name == "No ISOs found":
            return "❌ Please select a valid ISO to check"
        else:
            return self.iso_manager.get_iso_status()

    @safe_method(module_attr='iso_manager', error_prefix='ISO deletion')
    def delete_iso(self, folder_name: str) -> str:
        """Delete ISO and its directory"""
        if folder_name == "No ISOs found":
            return "❌ Please select a valid ISO to delete"
        return self.iso_manager.delete_iso(folder_name)

    @safe_method(module_attr='iso_manager', error_prefix='ISO summary')
    def get_iso_summary(self) -> str:
        """Get brief summary of ISO management for UI"""
        return self.iso_manager.get_summary()


def build_gradio_ui():
    """Build the main Gradio interface with enhanced Ubuntu management"""

    # Initialize UI controller
    ui = PXEBootStationUI()

    # Custom CSS for better styling
    custom_css = """
    .gradio-container {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .tab-nav {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
    .status-good { color: #28a745; }
    .status-warning { color: #ffc107; }
    .status-error { color: #dc3545; }
    """

    with gr.Blocks(
            title="🚀 PXE Boot Station",
            theme=gr.themes.Soft(),
            css=custom_css
    ) as demo:
        gr.HTML("""
        <div style="text-align: center; padding: 20px; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 10px; margin-bottom: 20px;">
            <h1>🚀 PXE Boot Station Control Panel</h1>
            <p>Complete PXE network boot management solution</p>
        </div>
        """)

        with gr.Tabs():
            # =========================
            # SYSTEM STATUS TAB
            # =========================
            with gr.Tab("📊 System Status", elem_id="status-tab"):
                gr.Markdown("## 🖥️ System Status & Health Monitor")

                with gr.Row():
                    refresh_btn, export_btn = _create_action_buttons(
                        ("Refresh Status", "primary", "🔄"),
                        ("Export JSON", "secondary", "📄")
                    )

                status_output = _create_status_textbox(
                    label="System Status",
                    initial_value=ui.get_system_status_display(),
                    lines=25,
                    max_lines=50,
                    show_label=False
                )

                refresh_btn.click(
                    fn=ui.refresh_system_status,
                    outputs=status_output
                )

                export_btn.click(
                    fn=ui.export_system_status,
                    outputs=_create_status_textbox(label="JSON Export", lines=5)
                )

            # =========================
            # TESTING TAB
            # =========================
            with gr.Tab("🧪 System Testing", elem_id="testing-tab"):
                gr.Markdown("## 🧪 System & Network Testing")

                with gr.Column():
                    with gr.Row():
                        full_test_btn, quick_test_btn = _create_action_buttons(
                            ("Run Full System Test", "primary", "🚀"),
                            ("Quick Network Test", "secondary", "⚡")
                        )

                    test_output = _create_status_textbox(
                        label="Test Results",
                        lines=15,
                        max_lines=30
                    )

                    full_test_btn.click(
                        fn=ui.run_full_system_test,
                        outputs=test_output
                    )

                    quick_test_btn.click(
                        fn=ui.run_legacy_http_test,
                        outputs=test_output
                    )

                with gr.Accordion("🔧 Manual Testing Tools", open=False):
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### TFTP Test")
                            tftp_host = gr.Textbox(value="localhost", label="TFTP Host")
                            tftp_port = gr.Number(value=69, label="TFTP Port", precision=0)
                            tftp_file = gr.Textbox(value="undionly.kpxe", label="Test File")
                            tftp_test_btn = gr.Button("Test TFTP")

                        with gr.Column():
                            gr.Markdown("### HTTP Test")
                            http_url = gr.Textbox(value="http://localhost:8000/status", label="HTTP URL")
                            http_timeout = gr.Number(value=5, label="Timeout (s)", precision=0)
                            http_test_btn = gr.Button("Test HTTP")

                        with gr.Column():
                            gr.Markdown("### File Check")
                            file_path = gr.Textbox(value="/srv/tftp/undionly.kpxe", label="File Path")
                            file_test_btn = gr.Button("Check File")

                    manual_test_output = _create_status_textbox(
                        label="Manual Test Results",
                        lines=5
                    )

                    tftp_test_btn.click(
                        fn=ui.test_tftp_connection,
                        inputs=[tftp_host, tftp_port, tftp_file],
                        outputs=manual_test_output
                    )

                    http_test_btn.click(
                        fn=ui.test_http_endpoint,
                        inputs=[http_url, http_timeout],
                        outputs=manual_test_output
                    )

                    file_test_btn.click(
                        fn=ui.check_file_exists,
                        inputs=[file_path],
                        outputs=manual_test_output
                    )

            # =========================
            # DHCP CONFIGURATION TAB
            # =========================
            with gr.Tab("🌐 DHCP Configuration", elem_id="dhcp-tab"):
                gr.Markdown("## 🌐 DHCP Server Configuration Generator")

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Network Configuration")
                        server_ip = gr.Textbox(
                            value="192.168.1.10",
                            label="PXE Server IP Address",
                            placeholder="192.168.1.10"
                        )
                        subnet = gr.Textbox(
                            value="192.168.1.0",
                            label="Subnet Address",
                            placeholder="192.168.1.0"
                        )
                        netmask = gr.Textbox(
                            value="255.255.255.0",
                            label="Subnet Mask",
                            placeholder="255.255.255.0"
                        )
                        router_ip = gr.Textbox(
                            value="192.168.1.1",
                            label="Default Gateway",
                            placeholder="192.168.1.1"
                        )
                        dns_servers = gr.Textbox(
                            value="8.8.8.8, 8.8.4.4",
                            label="DNS Servers (comma-separated)",
                            placeholder="8.8.8.8, 8.8.4.4"
                        )

                    with gr.Column():
                        gr.Markdown("### DHCP Settings")
                        config_type = gr.Dropdown(
                            choices=["isc", "dnsmasq", "mikrotik"],
                            value="isc",
                            label="DHCP Server Type"
                        )
                        lease_time = gr.Number(
                            value=86400,
                            label="Lease Time (seconds)",
                            precision=0
                        )
                        domain_name = gr.Textbox(
                            value="",
                            label="Domain Name (optional)",
                            placeholder="example.com"
                        )

                        with gr.Row():
                            generate_btn, save_btn = _create_action_buttons(
                                ("Generate Config", "primary", "🔧"),
                                ("Save Config", "secondary", "💾")
                            )

                dhcp_status = _create_status_textbox(
                    label="Status",
                    lines=2
                )

                dhcp_config_output = gr.Code(
                    label="Generated DHCP Configuration",
                    language="shell",
                    lines=15,
                    interactive=False
                )

                generate_btn.click(
                    fn=ui.generate_dhcp_config,
                    inputs=[server_ip, subnet, netmask, router_ip, dns_servers,
                            config_type, lease_time, domain_name],
                    outputs=[dhcp_status, dhcp_config_output]
                )

                save_btn.click(
                    fn=ui.save_dhcp_config,
                    inputs=[dhcp_config_output, config_type],
                    outputs=dhcp_status
                )

                with gr.Accordion("🚀 Quick Setup", open=False):
                    gr.Markdown("### Simple Network Configuration")
                    with gr.Row():
                        simple_server_ip = gr.Textbox(
                            value="192.168.1.10",
                            label="Server IP"
                        )
                        simple_network = gr.Textbox(
                            value="192.168.1.0/24",
                            label="Network CIDR"
                        )
                        simple_generate_btn = gr.Button("⚡ Quick Generate")

                    simple_generate_btn.click(
                        fn=ui.create_simple_dhcp_config,
                        inputs=[simple_server_ip, simple_network],
                        outputs=[dhcp_status, dhcp_config_output]
                    )

            # =========================
            # iPXE MENU TAB - ENHANCED
            # =========================
            with gr.Tab("📋 iPXE Menu", elem_id="ipxe-tab"):
                gr.Markdown("## 📋 Enhanced iPXE Boot Menu Configuration")

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Smart Menu Generation")

                        menu_type = gr.Dropdown(
                            choices=[
                                ("Multi-Mode Menu (All Options)", "multi"),
                                ("Quick Menu (Netboot Only)", "quick")
                            ],
                            value="multi",
                            label="Menu Type"
                        )

                        ipxe_server_ip = gr.Textbox(
                            value="192.168.1.10",
                            label="PXE Server IP"
                        )
                        ipxe_port = gr.Number(
                            value=8000,
                            label="HTTP Port",
                            precision=0
                        )

                        with gr.Row():
                            create_smart_btn, analyze_btn, suggest_iso_btn = _create_action_buttons(
                                ("Create Smart Menu", "primary", "🎨"),
                                ("Analyze Ubuntu Files", "secondary", "🔍"),
                                ("ISO Suggestions", "secondary", "💿")
                            )

                # Status and output areas
                with gr.Row():
                    with gr.Column():
                        ipxe_status = _create_status_textbox(
                            label="Menu Status",
                            lines=8
                        )

                    with gr.Column():
                        ubuntu_analysis = _create_status_textbox(
                            label="Ubuntu Analysis",
                            lines=8
                        )

                # iPXE script output
                ipxe_script_output = gr.Code(
                    label="Generated iPXE Boot Script",
                    language="shell",
                    lines=25,
                    interactive=True
                )

                with gr.Row():
                    validate_btn, save_ipxe_btn = _create_action_buttons(
                        ("Validate Script", "secondary", "✅"),
                        ("Save Menu", "primary", "💾")
                    )

                # Original template section for backward compatibility
                with gr.Accordion("🎨 Classic Templates", open=False):
                    gr.Markdown("### Original Template Selection")

                    template_choice = gr.Dropdown(
                        choices=["ubuntu", "diagnostic", "multi_os"],
                        value="ubuntu",
                        label="Classic Template"
                    )

                    create_template_btn = gr.Button("🎨 Create from Classic Template")

                    create_template_btn.click(
                        fn=ui.create_ipxe_menu_from_template,
                        inputs=[template_choice, ipxe_server_ip, ipxe_port],
                        outputs=[ipxe_status, ipxe_script_output]
                    )

                # Event handlers for new buttons
                create_smart_btn.click(
                    fn=ui.create_smart_ubuntu_menu,
                    inputs=[menu_type, ipxe_server_ip, ipxe_port],
                    outputs=[ipxe_status, ipxe_script_output]
                )

                analyze_btn.click(
                    fn=ui.get_ubuntu_capabilities_status,
                    outputs=ubuntu_analysis
                )

                suggest_iso_btn.click(
                    fn=ui.create_ubuntu_iso_download_suggestions,
                    outputs=ubuntu_analysis
                )

                validate_btn.click(
                    fn=ui.validate_ipxe_script,
                    inputs=[ipxe_script_output],
                    outputs=ipxe_status
                )

                save_ipxe_btn.click(
                    fn=ui.save_ipxe_menu,
                    inputs=[ipxe_script_output],
                    outputs=ipxe_status
                )

                # Keep existing custom entry section
                with gr.Accordion("➕ Add Custom Entry", open=False):
                    gr.Markdown("### Add Custom Boot Entry")
                    with gr.Row():
                        with gr.Column():
                            entry_name = gr.Textbox(label="Entry Name (ID)", placeholder="my_custom_os")
                            entry_title = gr.Textbox(label="Display Title", placeholder="My Custom OS")
                            entry_description = gr.Textbox(label="Description (optional)")

                        with gr.Column():
                            entry_kernel = gr.Textbox(label="Kernel Path", placeholder="custom/vmlinuz")
                            entry_initrd = gr.Textbox(label="Initrd Path (optional)", placeholder="custom/initrd")
                            entry_cmdline = gr.Textbox(label="Kernel Command Line", placeholder="ip=dhcp root=/dev/nfs")

                    add_entry_btn = gr.Button("➕ Add Entry to Menu")

                    add_entry_btn.click(
                        fn=ui.add_custom_ipxe_entry,
                        inputs=[ipxe_script_output, entry_name, entry_title, entry_kernel,
                                entry_initrd, entry_cmdline, entry_description],
                        outputs=ipxe_script_output
                    )

                # Sample menu preview
                with gr.Accordion("📋 Sample Multi-Mode Menu", open=False):
                    gr.Markdown("""
                    ### Example of Generated Smart Menu:

                    ```
                    Ubuntu Multi-Mode PXE Boot
                    ════════════════════════════════════════════════
                    Ubuntu Installation Options
                    ── Ubuntu 24.04 LTS ──
                    🌐 Ubuntu 24.04 - Network Install
                    💿 Ubuntu 24.04 - Live Boot         (if ISO available)
                    ⚡ Ubuntu 24.04 - Auto Install      (if preseed available)
                    🔧 Ubuntu 24.04 - Rescue Mode

                    ── Ubuntu 22.04 LTS ──  
                    🌐 Ubuntu 22.04 - Network Install
                    🔧 Ubuntu 22.04 - Rescue Mode

                    System Tools
                    🛠️ Memory Test (Memtest86+)

                    🖥️  Drop to iPXE shell
                    🔄 Reboot computer
                    ❌ Exit to BIOS
                    ```

                    **Boot Mode Indicators:**
                    - 🌐 Network Install: Downloads from Ubuntu repositories (requires internet)
                    - 💿 Live Boot: Boots from local ISO file (requires ISO)
                    - ⚡ Auto Install: Uses preseed configuration (requires preseed.cfg)
                    - 🔧 Rescue Mode: Recovery and repair tools (always available)
                    """)

            # =========================
            # UBUNTU DOWNLOAD TAB - ENHANCED
            # =========================
            with gr.Tab("🐧 Ubuntu Download", elem_id="ubuntu-tab"):
                gr.Markdown("## 🐧 Ubuntu Files Download & Management")

                # Summary section
                with gr.Row():
                    with gr.Column():
                        summary_output = _create_status_textbox(
                            label="Ubuntu Versions Summary",
                            initial_value=ui.get_ubuntu_summary(),
                            lines=4
                        )
                        refresh_summary_btn = gr.Button("🔄 Refresh Summary", variant="secondary", size="sm")

                # Download section
                gr.Markdown("### 📥 Download New Version")
                with gr.Row():
                    with gr.Column():
                        ubuntu_version = gr.Dropdown(
                            choices=["24.04", "22.04", "20.04"],
                            value="24.04",
                            label="Ubuntu Version to Download"
                        )

                        with gr.Row():
                            download_btn, check_all_btn = _create_action_buttons(
                                ("Download Ubuntu Files", "primary", "⬇️"),
                                ("Check All Versions", "secondary", "🔍")
                            )

                download_status = _create_status_textbox(
                    label="Download Status",
                    lines=12
                )

                # Management section
                gr.Markdown("### 🔧 Manage Installed Versions")
                with gr.Row():
                    with gr.Column():
                        installed_versions = gr.Dropdown(
                            choices=ui.get_installed_ubuntu_versions(),
                            value=ui.get_installed_ubuntu_versions()[0] if ui.get_installed_ubuntu_versions() and
                                                                           ui.get_installed_ubuntu_versions()[
                                                                               0] != "No versions installed" else "No versions installed",
                            label="Installed Versions",
                            allow_custom_value=False
                        )

                        with gr.Row():
                            check_version_btn, refresh_versions_btn, delete_version_btn = _create_action_buttons(
                                ("Check Version", "secondary", "🔍"),
                                ("Refresh List", "secondary", "🔄"),
                                ("Delete Version", "stop", "🗑️")
                            )

                        with gr.Row():
                            delete_all_btn = gr.Button("🗑️ Delete All Versions", variant="stop")

                management_status = _create_status_textbox(
                    label="Management Status",
                    lines=8
                )

                # Event handlers
                download_btn.click(
                    fn=ui.download_ubuntu_files,
                    inputs=[ubuntu_version],
                    outputs=download_status,
                    show_progress=True
                )

                check_all_btn.click(
                    fn=ui.check_ubuntu_files,
                    outputs=download_status
                )

                check_version_btn.click(
                    fn=ui.check_specific_ubuntu_version,
                    inputs=[installed_versions],
                    outputs=management_status
                )

                refresh_versions_btn.click(
                    fn=ui.refresh_ubuntu_versions_dropdown,
                    outputs=installed_versions
                )

                delete_version_btn.click(
                    fn=ui.delete_ubuntu_version,
                    inputs=[installed_versions],
                    outputs=management_status
                ).then(
                    fn=ui.refresh_ubuntu_versions_dropdown,
                    outputs=installed_versions
                ).then(
                    fn=ui.get_ubuntu_summary,
                    outputs=summary_output
                )

                delete_all_btn.click(
                    fn=ui.delete_all_ubuntu_versions,
                    outputs=management_status
                ).then(
                    fn=ui.refresh_ubuntu_versions_dropdown,
                    outputs=installed_versions
                ).then(
                    fn=ui.get_ubuntu_summary,
                    outputs=summary_output
                )

                refresh_summary_btn.click(
                    fn=ui.get_ubuntu_summary,
                    outputs=summary_output
                )

            # =========================
            # ISO MANAGEMENT TAB - ENHANCED WITH EXTRACTION
            # =========================
            with gr.Tab("📁 ISO Management", elem_id="iso-tab"):
                gr.Markdown("## 📁 ISO Images Download & Management")

                # Summary section
                with gr.Row():
                    with gr.Column():
                        iso_summary_output = _create_status_textbox(
                            label="ISO Images Summary",
                            initial_value=ui.get_iso_summary(),
                            lines=5
                        )
                        refresh_iso_summary_btn = gr.Button("🔄 Refresh Summary", variant="secondary", size="sm")

                # Download from URL section
                gr.Markdown("### 🌐 Download ISO from URL")
                with gr.Row():
                    with gr.Column():
                        iso_url = gr.Textbox(
                            label="ISO Download URL",
                            placeholder="https://example.com/my-disk.iso",
                            lines=1
                        )

                        with gr.Row():
                            iso_folder_name = gr.Textbox(
                                label="Folder Name",
                                placeholder="my-rescue-disk",
                                scale=2
                            )
                            iso_display_name = gr.Textbox(
                                label="Display Name",
                                placeholder="My Rescue Disk",
                                scale=2
                            )
                            iso_category = gr.Dropdown(
                                choices=list(ui.iso_manager.get_categories().keys()) if ui.iso_manager else [
                                    "custom"],
                                value="custom",
                                label="Category",
                                scale=1
                            )

                        # Extraction options for download
                        with gr.Accordion("📦 Boot File Extraction Options", open=False):
                            with gr.Row():
                                extract_files_download = gr.Checkbox(
                                    label="Extract boot files from ISO",
                                    value=False,
                                    info="Extract kernel, initrd, and config files for fast booting"
                                )

                            with gr.Row():
                                iso_retention_download = gr.Dropdown(
                                    choices=ui.get_iso_retention_options(),
                                    value="keep",
                                    label="ISO file handling after extraction",
                                    visible=False  # Will be shown when extract_files is checked
                                )

                        download_iso_btn = gr.Button("⬇️ Download ISO", variant="primary")

                # Upload file section
                gr.Markdown("### 📤 Upload ISO File")
                with gr.Row():
                    with gr.Column():
                        iso_file_upload = gr.File(
                            label="Select ISO File",
                            file_types=[".iso"],
                            file_count="single"
                        )

                        with gr.Row():
                            upload_folder_name = gr.Textbox(
                                label="Folder Name",
                                placeholder="my-utility",
                                scale=2
                            )
                            upload_display_name = gr.Textbox(
                                label="Display Name",
                                placeholder="My Utility Disk",
                                scale=2
                            )
                            upload_category = gr.Dropdown(
                                choices=list(ui.iso_manager.get_categories().keys()) if ui.iso_manager else [
                                    "custom"],
                                value="custom",
                                label="Category",
                                scale=1
                            )

                        # Extraction options for upload
                        with gr.Accordion("📦 Boot File Extraction Options", open=False):
                            with gr.Row():
                                extract_files_upload = gr.Checkbox(
                                    label="Extract boot files from ISO",
                                    value=False,
                                    info="Extract kernel, initrd, and config files for fast booting"
                                )

                            with gr.Row():
                                iso_retention_upload = gr.Dropdown(
                                    choices=ui.get_iso_retention_options(),
                                    value="keep",
                                    label="ISO file handling after extraction",
                                    visible=False  # Will be shown when extract_files is checked
                                )

                        upload_iso_btn = gr.Button("📤 Upload ISO", variant="primary")

                # Status output for downloads/uploads
                iso_operation_status = _create_status_textbox(
                    label="Operation Status",
                    lines=12
                )

                # Management section
                gr.Markdown("### 🔧 Manage Existing ISOs")
                with gr.Row():
                    with gr.Column():
                        # Get initial folder list
                        initial_folders = ui.get_iso_folder_names()

                        existing_isos = gr.Dropdown(
                            choices=initial_folders,
                            value=initial_folders[0],
                            label="Existing ISOs",
                            allow_custom_value=False
                        )

                        with gr.Row():
                            check_iso_btn, refresh_iso_list_btn, delete_iso_btn = _create_action_buttons(
                                ("Check ISO", "secondary", "🔍"),
                                ("Refresh List", "secondary", "🔄"),
                                ("Delete ISO", "stop", "🗑️")
                            )

                        check_all_isos_btn = gr.Button("📋 Check All ISOs", variant="secondary")

                iso_management_status = _create_status_textbox(
                    label="Management Status",
                    lines=10
                )

                # Show/hide retention options based on extraction checkbox
                extract_files_download.change(
                    fn=lambda checked: gr.update(visible=checked),
                    inputs=[extract_files_download],
                    outputs=[iso_retention_download]
                )

                extract_files_upload.change(
                    fn=lambda checked: gr.update(visible=checked),
                    inputs=[extract_files_upload],
                    outputs=[iso_retention_upload]
                )

                # Event handlers with extraction support
                download_iso_btn.click(
                    fn=ui.download_iso_from_url,
                    inputs=[iso_url, iso_folder_name, iso_display_name, iso_category,
                            extract_files_download, iso_retention_download],
                    outputs=iso_operation_status,
                    show_progress=True
                )

                upload_iso_btn.click(
                    fn=ui.upload_iso_file,
                    inputs=[iso_file_upload, upload_folder_name, upload_display_name, upload_category,
                            extract_files_upload, iso_retention_upload],
                    outputs=iso_operation_status
                )

                check_iso_btn.click(
                    fn=ui.get_iso_status,
                    inputs=[existing_isos],
                    outputs=iso_management_status
                )

                check_all_isos_btn.click(
                    fn=lambda: ui.get_iso_status(),
                    outputs=iso_management_status
                )

                refresh_iso_list_btn.click(
                    fn=ui.refresh_iso_list,
                    outputs=existing_isos
                )

                delete_iso_btn.click(
                    fn=ui.delete_iso,
                    inputs=[existing_isos],
                    outputs=iso_management_status
                ).then(
                    fn=ui.refresh_iso_list,
                    outputs=existing_isos
                ).then(
                    fn=ui.get_iso_summary,
                    outputs=iso_summary_output
                )

                refresh_iso_summary_btn.click(
                    fn=ui.get_iso_summary,
                    outputs=iso_summary_output
                )

                # Help section
                with gr.Accordion("ℹ️ Extraction Help", open=False):
                    gr.Markdown("""
                            ### 📦 Boot File Extraction

                            **When to use extraction:**
                            - ✅ **Linux rescue disks** - Extracts kernel/initrd for fast booting
                            - ✅ **Ubuntu/Debian live images** - Enables direct kernel boot  
                            - ✅ **Security tools** - Quick access without full ISO mount

                            **ISO file handling options:**
                            - 🏠 **Keep in same folder** - Original ISO + extracted files together
                            - 📁 **Move to iso/ subfolder** - Organized storage, saves space in main folder
                            - 🗑️ **Delete after extraction** - Maximum space savings, boot files only

                            **Boot options after extraction:**
                            - ⚡ **Fast boot** - Direct kernel loading (extracted files)
                            - 💿 **Full boot** - Complete ISO experience (sanboot/imgfetch)
                            - 🔧 **Flexible** - Choose boot method based on needs
                            """)

        # Footer
        gr.HTML("""
        <div style="text-align: center; padding: 20px; margin-top: 30px; border-top: 1px solid #ddd;">
            <p>🚀 <strong>PXE Boot Station</strong> - Network Boot Management Made Easy</p>
            <p style="color: #666;">Refactored Architecture • Clean Code • Enterprise Ready • Multi-Version Support</p>
        </div>
        """)

    return demo


# Create the demo instance
demo = build_gradio_ui()

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=9005,
        share=False,
        show_error=True,
        debug=False
    )
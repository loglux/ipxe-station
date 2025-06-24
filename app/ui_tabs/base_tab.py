import os
import gradio as gr
from typing import List, Tuple
from app.ui_tabs.helpers import safe_method
from app.backend.dhcp_config import DHCPConfigManager, create_simple_config
from app.backend.ipxe_manager import iPXEManager, iPXEEntry, iPXETemplateManager
from app.backend.iso_manager import ISOManager
from app.backend.system_status import SystemStatusManager
from app.backend.ubuntu_downloader import UbuntuDownloader
from app.tests import SystemTester
# from app.file_utils import FileManager

class PXEBootStationUI:
    """Main UI controller class with multi-version Ubuntu support"""

    def __init__(self):
        # Initialize components with fallbacks
        self.system_tester = SystemTester() if SystemTester else None
        self.dhcp_manager = DHCPConfigManager() if DHCPConfigManager else None
        self.ipxe_manager = iPXEManager() if iPXEManager else None
        self.status_manager = SystemStatusManager() if SystemStatusManager else None
        self.ubuntu_downloader = UbuntuDownloader() if UbuntuDownloader else None
        # self.file_manager = FileManager() if FileManager else None
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
        if not self.system_tester:
            return "❌ System tester not available"
        return self.system_tester.http_tester.test_endpoint("http://localhost:8000/status")

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
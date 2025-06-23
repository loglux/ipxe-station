"""
Gradio Web UI for PXE Boot Station - Multi-version Ubuntu Support
Refactored to use modular architecture with enhanced Ubuntu management
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


    # =========================
    # SYSTEM STATUS TAB
    # =========================

    def get_system_status_display(self) -> str:
        """Get formatted system status for display"""
        try:
            if not self.status_manager:
                return "❌ System status module not available"

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

        except Exception as e:
            return f"❌ Error getting system status: {str(e)}"

    def refresh_system_status(self) -> str:
        """Refresh system status"""
        return self.get_system_status_display()

    def export_system_status(self) -> str:
        """Export system status as JSON"""
        try:
            if not self.status_manager:
                return "❌ System status module not available"
            return self.status_manager.export_status_json()
        except Exception as e:
            return f"❌ Export failed: {str(e)}"

    # =========================
    # TESTING TAB
    # =========================

    def run_full_system_test(self) -> str:
        """Run comprehensive system test"""
        try:
            if not self.system_tester:
                return "❌ System testing module not available"
            return self.system_tester.run_full_system_test()
        except Exception as e:
            return f"❌ Test failed: {str(e)}"

    def test_tftp_connection(self, host: str = "localhost", port: int = 69,
                             filename: str = "undionly.kpxe", timeout: int = 5) -> str:
        """Test TFTP connection with custom parameters"""
        try:
            if not self.system_tester:
                return "❌ System testing module not available"
            return self.system_tester.tftp_tester.test_tftp_connection(host, port, filename, timeout)
        except Exception as e:
            return f"❌ TFTP test failed: {str(e)}"

    def test_http_endpoint(self, url: str = "http://localhost:8000/status", timeout: int = 5) -> str:
        """Test HTTP endpoint"""
        try:
            if not self.system_tester:
                return "❌ System testing module not available"
            return self.system_tester.http_tester.test_endpoint(url, timeout)
        except Exception as e:
            return f"❌ HTTP test failed: {str(e)}"

    def check_file_exists(self, filepath: str) -> str:
        """Check if file exists"""
        try:
            if not self.system_tester:
                return "❌ System testing module not available"
            return self.system_tester.file_checker.check_file_exists(filepath)
        except Exception as e:
            return f"❌ File check failed: {str(e)}"

    def run_legacy_http_test(self) -> str:
        """Run legacy HTTP test"""
        try:
            if not legacy_test_http_endpoints:
                return "❌ Legacy test function not available"
            return legacy_test_http_endpoints()
        except Exception as e:
            return f"❌ Legacy test failed: {str(e)}"

    # =========================
    # DHCP CONFIGURATION TAB
    # =========================

    def generate_dhcp_config(self, server_ip: str, subnet: str, netmask: str,
                             router_ip: str, dns_servers: str, config_type: str,
                             lease_time: int = 86400, domain_name: str = "") -> Tuple[str, str]:
        """Generate DHCP configuration"""
        try:
            if not self.dhcp_manager:
                return "❌ DHCP configuration module not available", ""

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

        except Exception as e:
            return f"❌ DHCP config generation failed: {str(e)}", ""

    def save_dhcp_config(self, config_content: str, config_type: str) -> str:
        """Save DHCP configuration to file"""
        try:
            if not self.dhcp_manager:
                return "❌ DHCP configuration module not available"

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

        except Exception as e:
            return f"❌ Failed to save DHCP config: {str(e)}"

    def create_simple_dhcp_config(self, server_ip: str, network_cidr: str) -> Tuple[str, str]:
        """Create simple DHCP configuration from CIDR"""
        try:
            if not self.dhcp_manager or not create_simple_config:
                return "❌ DHCP configuration module not available", ""

            config = create_simple_config(server_ip, network_cidr)
            is_valid, message, config_content = self.dhcp_manager.validate_and_generate(config, "isc")
            return message, config_content if is_valid else ""
        except Exception as e:
            return f"❌ Simple config failed: {str(e)}", ""

    # =========================
    # iPXE MENU TAB
    # =========================

    def create_ipxe_menu_from_template(self, template_name: str, server_ip: str = "localhost",
                                       port: int = 8000) -> Tuple[str, str]:
        """Create iPXE menu from template with auto-detection of Ubuntu versions"""
        try:
            if not self.ipxe_manager:
                return "❌ iPXE manager module not available", ""

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

        except Exception as e:
            return f"❌ Template creation failed: {str(e)}", ""

    def save_ipxe_menu(self, script_content: str) -> str:
        """Save iPXE menu script"""
        try:
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

        except Exception as e:
            return f"❌ Failed to save iPXE menu: {str(e)}"

    def add_custom_ipxe_entry(self, menu_script: str, entry_name: str, entry_title: str,
                              kernel_path: str, initrd_path: str = "", cmdline: str = "",
                              description: str = "") -> str:
        """Add custom entry to iPXE menu"""
        try:
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

        except Exception as e:
            return f"❌ Failed to add entry: {str(e)}"

    def validate_ipxe_script(self, script_content: str) -> str:
        """Validate iPXE script"""
        try:
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

        except Exception as e:
            return f"❌ Validation failed: {str(e)}"

    # =========================
    # UBUNTU DOWNLOAD TAB - ENHANCED
    # =========================

    def download_ubuntu_files(self, version: str = "22.04", progress=gr.Progress()) -> str:
        """Download Ubuntu files with progress tracking"""
        try:
            if not self.ubuntu_downloader:
                return "❌ Ubuntu downloader module not available"

            def progress_callback(current: int, total: int, filename: str):
                if total > 0:
                    percent = (current / total) * 100
                    progress(percent / 100, desc=f"Downloading {filename}")

            result = self.ubuntu_downloader.download_all_files(
                version=version,
                progress_callback=progress_callback
            )

            return result

        except Exception as e:
            return f"❌ Ubuntu download failed: {str(e)}"

    def check_ubuntu_files(self) -> str:
        """Check all Ubuntu files status"""
        try:
            if not self.ubuntu_downloader:
                return "❌ Ubuntu downloader module not available"
            return self.ubuntu_downloader.check_files_status()
        except Exception as e:
            return f"❌ Ubuntu check failed: {str(e)}"

    def check_specific_ubuntu_version(self, version: str) -> str:
        """Check files for specific Ubuntu version"""
        try:
            if not self.ubuntu_downloader:
                return "❌ Ubuntu downloader module not available"

            if not version or version in ["No versions installed", "Error"]:
                return "❌ Please select a valid version to check"

            return self.ubuntu_downloader.check_files_status(version)
        except Exception as e:
            return f"❌ Ubuntu version check failed: {str(e)}"

    def get_installed_ubuntu_versions(self) -> list:
        """Get list of installed Ubuntu versions for dropdown"""
        try:
            if not self.ubuntu_downloader:
                return ["No versions found"]

            installed = self.ubuntu_downloader.get_installed_versions()
            return installed if installed else ["No versions installed"]
        except Exception as e:
            return ["Error loading versions"]

    def delete_ubuntu_version(self, version: str) -> str:
        """Delete specific Ubuntu version"""
        try:
            if not self.ubuntu_downloader:
                return "❌ Ubuntu downloader module not available"

            if not version or version in ["No versions installed", "Error"]:
                return "❌ Please select a valid version to delete"

            return self.ubuntu_downloader.delete_version(version)
        except Exception as e:
            return f"❌ Ubuntu deletion failed: {str(e)}"

    def delete_all_ubuntu_versions(self) -> str:
        """Delete all Ubuntu versions"""
        try:
            if not self.ubuntu_downloader:
                return "❌ Ubuntu downloader module not available"

            return self.ubuntu_downloader.delete_all_versions()
        except Exception as e:
            return f"❌ Ubuntu deletion failed: {str(e)}"

    def refresh_ubuntu_versions_dropdown(self) -> dict:
        """Refresh the installed versions dropdown"""
        try:
            versions = self.get_installed_ubuntu_versions()
            return gr.update(choices=versions, value=versions[0] if versions and versions[
                0] != "No versions installed" else "No versions installed")
        except Exception as e:
            return gr.update(choices=["Error"], value="Error")

    def get_ubuntu_summary(self) -> str:
        """Get Ubuntu installations summary"""
        try:
            if not self.ubuntu_downloader:
                return "❌ Ubuntu downloader module not available"

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

        except Exception as e:
            return f"❌ Error getting summary: {str(e)}"

    def create_smart_ubuntu_menu(self, template_type: str = "multi", server_ip: str = "localhost",
                                 port: int = 8000) -> Tuple[str, str]:
        """Create smart Ubuntu menu with multiple boot options"""
        try:
            if not self.ipxe_manager:
                return "❌ iPXE manager module not available", ""

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

        except Exception as e:
            return f"❌ Smart menu creation failed: {str(e)}", ""

    def get_ubuntu_capabilities_status(self) -> str:
        """Get detailed Ubuntu capabilities status"""
        try:
            if not self.ipxe_manager:
                return "❌ iPXE manager module not available"

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

        except Exception as e:
            return f"❌ Analysis failed: {str(e)}"

    def create_ubuntu_iso_download_suggestions(self) -> str:
        """Generate suggestions for downloading missing ISO files"""
        try:
            if not self.ipxe_manager:
                return "❌ iPXE manager module not available"

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

        except Exception as e:
            return f"❌ Suggestion generation failed: {str(e)}"


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
                    refresh_btn = gr.Button("🔄 Refresh Status", variant="primary")
                    export_btn = gr.Button("📄 Export JSON", variant="secondary")

                status_output = gr.Textbox(
                    label="System Status",
                    value=ui.get_system_status_display(),
                    lines=25,
                    max_lines=50,
                    interactive=False,
                    show_label=False
                )

                refresh_btn.click(
                    fn=ui.refresh_system_status,
                    outputs=status_output
                )

                export_btn.click(
                    fn=ui.export_system_status,
                    outputs=gr.Textbox(label="JSON Export", lines=5)
                )

            # =========================
            # TESTING TAB
            # =========================
            with gr.Tab("🧪 System Testing", elem_id="testing-tab"):
                gr.Markdown("## 🧪 System & Network Testing")

                with gr.Column():
                    with gr.Row():
                        full_test_btn = gr.Button("🚀 Run Full System Test", variant="primary")
                        quick_test_btn = gr.Button("⚡ Quick Network Test", variant="secondary")

                    test_output = gr.Textbox(
                        label="Test Results",
                        lines=15,
                        max_lines=30,
                        interactive=False
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

                    manual_test_output = gr.Textbox(
                        label="Manual Test Results",
                        lines=5,
                        interactive=False
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
                            generate_btn = gr.Button("🔧 Generate Config", variant="primary")
                            save_btn = gr.Button("💾 Save Config", variant="secondary")

                dhcp_status = gr.Textbox(
                    label="Status",
                    lines=2,
                    interactive=False
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
                            create_smart_btn = gr.Button("🎨 Create Smart Menu", variant="primary")
                            analyze_btn = gr.Button("🔍 Analyze Ubuntu Files", variant="secondary")
                            suggest_iso_btn = gr.Button("💿 ISO Suggestions", variant="secondary")

                # Status and output areas
                with gr.Row():
                    with gr.Column():
                        ipxe_status = gr.Textbox(
                            label="Menu Status",
                            lines=8,
                            interactive=False
                        )

                    with gr.Column():
                        ubuntu_analysis = gr.Textbox(
                            label="Ubuntu Analysis",
                            lines=8,
                            interactive=False
                        )

                # iPXE script output
                ipxe_script_output = gr.Code(
                    label="Generated iPXE Boot Script",
                    language="shell",
                    lines=25,
                    interactive=True
                )

                with gr.Row():
                    validate_btn = gr.Button("✅ Validate Script", variant="secondary")
                    save_ipxe_btn = gr.Button("💾 Save Menu", variant="primary")

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
                        summary_output = gr.Textbox(
                            label="Ubuntu Versions Summary",
                            value=ui.get_ubuntu_summary(),
                            lines=4,
                            interactive=False
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
                            download_btn = gr.Button("⬇️ Download Ubuntu Files", variant="primary")
                            check_all_btn = gr.Button("🔍 Check All Versions", variant="secondary")

                download_status = gr.Textbox(
                    label="Download Status",
                    lines=12,
                    interactive=False
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
                            check_version_btn = gr.Button("🔍 Check Version", variant="secondary")
                            refresh_versions_btn = gr.Button("🔄 Refresh List", variant="secondary")
                            delete_version_btn = gr.Button("🗑️ Delete Version", variant="stop")

                        with gr.Row():
                            delete_all_btn = gr.Button("🗑️ Delete All Versions", variant="stop")

                management_status = gr.Textbox(
                    label="Management Status",
                    lines=8,
                    interactive=False
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
            # ISO MANAGEMENT TAB
            # =========================
            with gr.Tab("📁 ISO Management", elem_id="iso-tab"):
                gr.Markdown("## 📁 ISO Images Download & Management")

                # Summary section
                with gr.Row():
                    with gr.Column():
                        iso_summary_output = gr.Textbox(
                            label="ISO Images Summary",
                            value=ui.get_iso_summary(),
                            lines=4,
                            interactive=False
                        )
                        refresh_iso_summary_btn = gr.Button("🔄 Refresh Summary", variant="secondary", size="sm")

                # Download from URL section
                gr.Markdown("### 🌐 Download ISO from URL")
                with gr.Row():
                    with gr.Column():
                        iso_url = gr.Textbox(
                            label="ISO Download URL",
                            placeholder="https://example.com/rescue-disk.iso",
                            lines=1
                        )

                        with gr.Row():
                            iso_folder_name = gr.Textbox(
                                label="Folder Name",
                                placeholder="kaspersky-rescue",
                                scale=2
                            )
                            iso_display_name = gr.Textbox(
                                label="Display Name",
                                placeholder="Kaspersky Rescue Disk",
                                scale=2
                            )
                            iso_category = gr.Dropdown(
                                choices=ui.get_iso_categories(),
                                value="custom",
                                label="Category",
                                scale=1
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
                                placeholder="custom-utility",
                                scale=2
                            )
                            upload_display_name = gr.Textbox(
                                label="Display Name",
                                placeholder="Custom Utility Disk",
                                scale=2
                            )
                            upload_category = gr.Dropdown(
                                choices=ui.get_iso_categories(),
                                value="custom",
                                label="Category",
                                scale=1
                            )

                        upload_iso_btn = gr.Button("📤 Upload ISO", variant="primary")

                # Status output for downloads/uploads
                iso_operation_status = gr.Textbox(
                    label="Operation Status",
                    lines=10,
                    interactive=False
                )

                # Management section
                gr.Markdown("### 🔧 Manage Existing ISOs")
                with gr.Row():
                    with gr.Column():
                        existing_isos = gr.Dropdown(
                            choices=ui.get_iso_folders_list(),
                            value=ui.get_iso_folders_list()[0] if ui.get_iso_folders_list() and
                                                                  ui.get_iso_folders_list()[
                                                                      0] != "No ISOs found" else "No ISOs found",
                            label="Existing ISOs",
                            allow_custom_value=False
                        )

                        with gr.Row():
                            check_iso_btn = gr.Button("🔍 Check ISO", variant="secondary")
                            refresh_iso_list_btn = gr.Button("🔄 Refresh List", variant="secondary")
                            delete_iso_btn = gr.Button("🗑️ Delete ISO", variant="stop")

                        check_all_isos_btn = gr.Button("📋 Check All ISOs", variant="secondary")

                iso_management_status = gr.Textbox(
                    label="Management Status",
                    lines=8,
                    interactive=False
                )

                # Event handlers for ISO management
                download_iso_btn.click(
                    fn=ui.download_iso_from_url,
                    inputs=[iso_url, iso_folder_name, iso_display_name, iso_category],
                    outputs=iso_operation_status,
                    show_progress=True
                )

                upload_iso_btn.click(
                    fn=ui.upload_iso_file,
                    inputs=[iso_file_upload, upload_folder_name, upload_display_name, upload_category],
                    outputs=iso_operation_status
                )

                check_iso_btn.click(
                    fn=ui.get_specific_iso_status,
                    inputs=[existing_isos],
                    outputs=iso_management_status
                )

                check_all_isos_btn.click(
                    fn=ui.get_existing_isos_status,
                    outputs=iso_management_status
                )

                refresh_iso_list_btn.click(
                    fn=ui.refresh_iso_dropdown,
                    outputs=existing_isos
                )

                delete_iso_btn.click(
                    fn=ui.delete_iso_folder,
                    inputs=[existing_isos],
                    outputs=iso_management_status
                ).then(
                    fn=ui.refresh_iso_dropdown,
                    outputs=existing_isos
                ).then(
                    fn=ui.get_iso_summary,
                    outputs=iso_summary_output
                )

                refresh_iso_summary_btn.click(
                    fn=ui.get_iso_summary,
                    outputs=iso_summary_output
                )


        # Footer
        gr.HTML("""
        <div style="text-align: center; padding: 20px; margin-top: 30px; border-top: 1px solid #ddd;">
            <p>🚀 <strong>PXE Boot Station</strong> - Network Boot Management Made Easy</p>
            <p style="color: #666;">Modular Architecture • Clean Code • Enterprise Ready • Multi-Version Support</p>
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
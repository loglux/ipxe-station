"""
Gradio Web UI for PXE Boot Station
Refactored to use modular architecture
"""

import gradio as gr
import json
import os
from typing import Dict, List, Tuple, Optional, Any

# Import our new modular components with error handling
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
    from file_utils import FileManager
except ImportError:
    FileManager = None


class PXEBootStationUI:
    """Main UI controller class"""

    def __init__(self):
        # Initialize components with fallbacks
        self.system_tester = SystemTester() if SystemTester else None
        self.dhcp_manager = DHCPConfigManager() if DHCPConfigManager else None
        self.ipxe_manager = iPXEManager() if iPXEManager else None
        self.status_manager = SystemStatusManager() if SystemStatusManager else None
        self.ubuntu_downloader = UbuntuDownloader() if UbuntuDownloader else None
        self.file_manager = FileManager() if FileManager else None
        self.ipxe_templates = iPXETemplateManager() if iPXETemplateManager else None

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
        """Create iPXE menu from template"""
        try:
            if not self.ipxe_manager:
                return "❌ iPXE manager module not available", ""

            menu = self.ipxe_manager.get_template(template_name, server_ip, port)
            if not menu:
                return f"❌ Template '{template_name}' not found", ""

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
    # UBUNTU DOWNLOAD TAB
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
        """Check Ubuntu files status"""
        try:
            if not self.ubuntu_downloader:
                return "❌ Ubuntu downloader module not available"
            return self.ubuntu_downloader.check_files_status()
        except Exception as e:
            return f"❌ Ubuntu check failed: {str(e)}"


def build_gradio_ui():
    """Build the main Gradio interface"""

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
            # iPXE MENU TAB
            # =========================
            with gr.Tab("📋 iPXE Menu", elem_id="ipxe-tab"):
                gr.Markdown("## 📋 iPXE Boot Menu Configuration")

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Template Selection")
                        template_choice = gr.Dropdown(
                            choices=["ubuntu", "diagnostic", "multi_os"],
                            value="ubuntu",
                            label="Menu Template"
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
                            create_template_btn = gr.Button("🎨 Create from Template", variant="primary")
                            validate_btn = gr.Button("✅ Validate Script", variant="secondary")
                            save_ipxe_btn = gr.Button("💾 Save Menu", variant="primary")

                ipxe_status = gr.Textbox(
                    label="Status",
                    lines=2,
                    interactive=False
                )

                ipxe_script_output = gr.Code(
                    label="iPXE Boot Script",
                    language="shell",
                    lines=20,
                    interactive=True
                )

                create_template_btn.click(
                    fn=ui.create_ipxe_menu_from_template,
                    inputs=[template_choice, ipxe_server_ip, ipxe_port],
                    outputs=[ipxe_status, ipxe_script_output]
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

            # =========================
            # UBUNTU DOWNLOAD TAB
            # =========================
            with gr.Tab("🐧 Ubuntu Download", elem_id="ubuntu-tab"):
                gr.Markdown("## 🐧 Ubuntu Files Download & Management")

                with gr.Row():
                    with gr.Column():
                        ubuntu_version = gr.Dropdown(
                            choices=["22.04", "20.04", "24.04"],
                            value="22.04",
                            label="Ubuntu Version"
                        )

                        with gr.Row():
                            download_btn = gr.Button("⬇️ Download Ubuntu Files", variant="primary")
                            check_btn = gr.Button("🔍 Check Files", variant="secondary")

                ubuntu_status = gr.Textbox(
                    label="Download Status",
                    lines=10,
                    interactive=False
                )

                download_btn.click(
                    fn=ui.download_ubuntu_files,
                    inputs=[ubuntu_version],
                    outputs=ubuntu_status,
                    show_progress=True
                )

                check_btn.click(
                    fn=ui.check_ubuntu_files,
                    outputs=ubuntu_status
                )

        # Footer
        gr.HTML("""
        <div style="text-align: center; padding: 20px; margin-top: 30px; border-top: 1px solid #ddd;">
            <p>🚀 <strong>PXE Boot Station</strong> - Network Boot Management Made Easy</p>
            <p style="color: #666;">Modular Architecture • Clean Code • Enterprise Ready</p>
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
"""
DHCP Configuration Tab for PXE Boot Station UI
Handles DHCP server configuration generation and validation
"""
# bear in mind: from app.dhcp_config import create_simple_config

import gradio as gr
from typing import Optional

from base_tab import BaseTab
from app.ui_helpers import safe_method


class DHCPTab(BaseTab):
    """DHCP Server Configuration Generator tab."""

    @property
    def tab_name(self) -> str:
        return "🌐 DHCP Configuration"

    @property
    def tab_id(self) -> str:
        return "dhcp-tab"

    def create_tab(self) -> gr.Tab:
        """Create the DHCP Configuration tab."""
        with gr.Tab(self.tab_name, elem_id=self.tab_id) as tab:
            # Tab header
            self._create_section_header(
                "DHCP Server Configuration Generator",
                icon="🌐",
                description="Generate DHCP server configurations for PXE boot"
            )

            # Configuration form section
            self._create_configuration_form()

            # Status and output section
            self._create_output_section()

            # Quick setup section (in accordion)
            self._create_quick_setup_section()

            # Setup event handlers
            self._setup_event_handlers()

        return tab

    def _create_configuration_form(self):
        """Create the main configuration form."""
        with gr.Row():
            # Network Configuration Column
            with gr.Column():
                self._create_section_header("Network Configuration", icon="🔧")

                self.server_ip = gr.Textbox(
                    value="192.168.1.10",
                    label="PXE Server IP Address",
                    placeholder="192.168.1.10",
                    info="IP address of this PXE server"
                )

                self.subnet = gr.Textbox(
                    value="192.168.1.0",
                    label="Subnet Address",
                    placeholder="192.168.1.0",
                    info="Network subnet address"
                )

                self.netmask = gr.Textbox(
                    value="255.255.255.0",
                    label="Subnet Mask",
                    placeholder="255.255.255.0",
                    info="Network subnet mask"
                )

                self.router_ip = gr.Textbox(
                    value="192.168.1.1",
                    label="Default Gateway",
                    placeholder="192.168.1.1",
                    info="Default gateway/router IP"
                )

                self.dns_servers = gr.Textbox(
                    value="8.8.8.8, 8.8.4.4",
                    label="DNS Servers (comma-separated)",
                    placeholder="8.8.8.8, 8.8.4.4",
                    info="DNS servers for clients"
                )

            # DHCP Settings Column
            with gr.Column():
                self._create_section_header("DHCP Settings", icon="⚙️")

                self.config_type = gr.Dropdown(
                    choices=["isc", "dnsmasq", "mikrotik"],
                    value="isc",
                    label="DHCP Server Type",
                    info="Type of DHCP server configuration to generate"
                )

                self.lease_time = gr.Number(
                    value=86400,
                    label="Lease Time (seconds)",
                    precision=0,
                    info="Default lease time (86400 = 24 hours)"
                )

                self.domain_name = gr.Textbox(
                    value="",
                    label="Domain Name (optional)",
                    placeholder="example.com",
                    info="Domain name for DHCP clients"
                )

                # Action buttons
                with gr.Row():
                    self.generate_btn, self.save_btn = self._create_action_buttons(
                        ("Generate Config", "primary", "🔧"),
                        ("Save Config", "secondary", "💾"),
                        component_keys=["generate_btn", "save_btn"]
                    )

    def _create_output_section(self):
        """Create status and output section."""
        # Status textbox
        self.dhcp_status = self._create_status_textbox(
            label="Status",
            lines=3,
            component_key="dhcp_status"
        )

        # Configuration output
        self.dhcp_config_output = gr.Code(
            label="Generated DHCP Configuration",
            language="shell",
            lines=15,
            interactive=False
        )
        self.store_component("dhcp_config_output", self.dhcp_config_output)

    def _create_quick_setup_section(self):
        """Create quick setup section."""
        with gr.Accordion("🚀 Quick Setup", open=False):
            self._create_info_box(
                "Generate DHCP configuration quickly using CIDR notation.",
                box_type="info"
            )

            self._create_section_header("Simple Network Configuration", icon="⚡")

            with gr.Row():
                self.simple_server_ip = gr.Textbox(
                    value="192.168.1.10",
                    label="Server IP",
                    info="PXE server IP address"
                )

                self.simple_network = gr.Textbox(
                    value="192.168.1.0/24",
                    label="Network CIDR",
                    info="Network in CIDR notation (e.g., 192.168.1.0/24)"
                )

                self.simple_generate_btn = gr.Button("⚡ Quick Generate", variant="primary")

    def _setup_event_handlers(self):
        """Setup all event handlers for the tab."""
        # Main generate button
        self.generate_btn.click(
            fn=self._generate_dhcp_config,
            inputs=[
                self.server_ip, self.subnet, self.netmask, self.router_ip,
                self.dns_servers, self.config_type, self.lease_time, self.domain_name
            ],
            outputs=[self.dhcp_status, self.dhcp_config_output]
        )

        # Save button
        self.save_btn.click(
            fn=self._save_dhcp_config,
            inputs=[self.dhcp_config_output, self.config_type],
            outputs=self.dhcp_status
        )

        # Quick generate button
        self.simple_generate_btn.click(
            fn=self._create_simple_dhcp_config,
            inputs=[self.simple_server_ip, self.simple_network],
            outputs=[self.dhcp_status, self.dhcp_config_output]
        )

    # =========================
    # TAB-SPECIFIC METHODS
    # =========================

    @safe_method(module_attr='dhcp_manager', error_prefix='DHCP configuration')
    def _generate_dhcp_config(self, server_ip: str, subnet: str, netmask: str,
                              router_ip: str, dns_servers: str, config_type: str,
                              lease_time: int = 86400, domain_name: str = "") -> tuple:
        """Generate DHCP configuration."""
        if not self.ui_controller.dhcp_manager:
            error_msg = "❌ DHCP manager module not available"
            return error_msg, ""

        try:
            # Parse DNS servers
            dns_list = [dns.strip() for dns in dns_servers.split(",") if dns.strip()]

            if not dns_list:
                return "❌ At least one DNS server is required", ""

            # Create config object
            config = self.ui_controller.dhcp_manager.create_config(
                server_ip=server_ip.strip(),
                subnet=subnet.strip(),
                netmask=netmask.strip(),
                router_ip=router_ip.strip(),
                dns_servers=dns_list,
                lease_time=int(lease_time),
                domain_name=domain_name.strip() if domain_name.strip() else None
            )

            # Validate and generate
            is_valid, message, config_content = self.ui_controller.dhcp_manager.validate_and_generate(
                config, config_type.lower()
            )

            return message, config_content if is_valid else ""

        except ValueError as e:
            return f"❌ Invalid input: {str(e)}", ""
        except Exception as e:
            return f"❌ Configuration generation failed: {str(e)}", ""

    @safe_method(module_attr='dhcp_manager', error_prefix='DHCP configuration save')
    def _save_dhcp_config(self, config_content: str, config_type: str) -> str:
        """Save DHCP configuration to file."""
        if not self.ui_controller.dhcp_manager:
            return "❌ DHCP manager module not available"

        if not config_content or not config_content.strip():
            return "❌ No configuration content to save"

        try:
            # Determine file path based on OS
            import os
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

            is_saved, message = self.ui_controller.dhcp_manager.save_config(
                config_content, filepath
            )

            return message

        except Exception as e:
            return f"❌ Save failed: {str(e)}"

    @safe_method(module_attr='dhcp_manager', error_prefix='Simple DHCP configuration')
    def _create_simple_dhcp_config(self, server_ip: str, network_cidr: str) -> tuple:
        """Create simple DHCP configuration from CIDR."""
        if not self.ui_controller.dhcp_manager:
            error_msg = "❌ DHCP manager module not available"
            return error_msg, ""

        try:
            # Import create_simple_config function
            from app.dhcp_config import create_simple_config

            if not create_simple_config:
                return "❌ Simple config function not available", ""

            # Validate inputs
            if not server_ip.strip():
                return "❌ Server IP is required", ""

            if not network_cidr.strip() or '/' not in network_cidr:
                return "❌ Network CIDR is required (e.g., 192.168.1.0/24)", ""

            config = create_simple_config(server_ip.strip(), network_cidr.strip())
            is_valid, message, config_content = self.ui_controller.dhcp_manager.validate_and_generate(
                config, "isc"
            )

            return message, config_content if is_valid else ""

        except Exception as e:
            return f"❌ Simple configuration failed: {str(e)}", ""

    # =========================
    # TAB VALIDATION
    # =========================

    def validate_tab(self) -> Optional[str]:
        """
        Validate that this tab can function properly.

        Returns:
            Error message if validation fails, None if successful
        """
        return self._validate_required_modules(['dhcp_manager'])

    # =========================
    # HELPER METHODS
    # =========================

    def _get_dhcp_templates(self) -> dict:
        """Get common DHCP configuration templates."""
        return {
            "home_network": {
                "server_ip": "192.168.1.10",
                "subnet": "192.168.1.0",
                "netmask": "255.255.255.0",
                "router_ip": "192.168.1.1",
                "dns_servers": "8.8.8.8, 8.8.4.4",
                "description": "Home network (192.168.1.x)"
            },
            "office_network": {
                "server_ip": "10.0.1.10",
                "subnet": "10.0.1.0",
                "netmask": "255.255.255.0",
                "router_ip": "10.0.1.1",
                "dns_servers": "8.8.8.8, 1.1.1.1",
                "description": "Office network (10.0.1.x)"
            },
            "lab_network": {
                "server_ip": "172.16.0.10",
                "subnet": "172.16.0.0",
                "netmask": "255.255.0.0",
                "router_ip": "172.16.0.1",
                "dns_servers": "8.8.8.8, 8.8.4.4",
                "description": "Lab network (172.16.x.x)"
            }
        }

    def get_configuration_summary(self) -> str:
        """Get summary of current DHCP configuration capabilities."""
        summary = []
        summary.append("🌐 **DHCP Configuration Features**")
        summary.append("=" * 40)

        if self.ui_controller.dhcp_manager:
            summary.append("✅ **DHCP Manager:** Available")
            summary.append("   • ISC DHCP Server configuration")
            summary.append("   • dnsmasq configuration")
            summary.append("   • MikroTik configuration")
            summary.append("   • Network validation")
            summary.append("   • Configuration saving")
        else:
            summary.append("❌ **DHCP Manager:** Not available")

        summary.append("")
        summary.append("🔧 **Supported Server Types:**")
        summary.append("   • **ISC DHCP** - Traditional DHCP server")
        summary.append("   • **dnsmasq** - Lightweight DHCP/DNS server")
        summary.append("   • **MikroTik** - RouterOS DHCP configuration")

        summary.append("")
        summary.append("💡 **Quick Setup Tips:**")
        summary.append("   • Use CIDR notation for quick configuration")
        summary.append("   • Ensure PXE server IP is in the same subnet")
        summary.append("   • Test configuration before deploying")

        return "\n".join(summary)

    def get_debug_info(self) -> str:
        """Get debug information for this tab."""
        info = [
            f"Tab: {self.tab_name}",
            f"Components: {len(self._components)}",
            f"DHCP Manager Available: {bool(self.ui_controller.dhcp_manager)}",
        ]

        validation_error = self.validate_tab()
        if validation_error:
            info.append(f"Validation Error: {validation_error}")
        else:
            info.append("Validation: ✅ Passed")

        return "\n".join(info)
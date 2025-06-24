from app.ui_tabs.base_tab import PXEBootStationUI
from app.ui_tabs.helpers import safe_method, _create_action_buttons, _create_status_textbox
import gradio as gr

class DHCPTab:
    def __init__(self, ui_controller: PXEBootStationUI):
        self.ui_controller = ui_controller

    def create_tab(self):
        with gr.Tab("🌐 DHCP Configuration"):
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
                fn=self.ui_controller.generate_dhcp_config,
                inputs=[server_ip, subnet, netmask, router_ip, dns_servers,
                        config_type, lease_time, domain_name],
                outputs=[dhcp_status, dhcp_config_output]
            )

            save_btn.click(
                fn=self.ui_controller.save_dhcp_config,
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
                    fn=self.ui_controller.create_simple_dhcp_config,
                    inputs=[simple_server_ip, simple_network],
                    outputs=[dhcp_status, dhcp_config_output]
                )

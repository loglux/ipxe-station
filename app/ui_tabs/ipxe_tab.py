from app.ui_tabs.base_tab import PXEBootStationUI
from app.ui_tabs.helpers import safe_method, _create_action_buttons, _create_status_textbox
import gradio as gr

class iPXETab:
    def __init__(self, ui_controller: PXEBootStationUI):
        self.ui_controller = ui_controller

    def create_tab(self):
        with gr.Tab("📋 iPXE Menu"):
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

            create_smart_btn.click(
                fn=self.ui_controller.create_smart_ubuntu_menu,
                inputs=[menu_type, ipxe_server_ip, ipxe_port],
                outputs=[ipxe_status, ipxe_script_output]
            )

            analyze_btn.click(
                fn=self.ui_controller.get_ubuntu_capabilities_status,
                outputs=ubuntu_analysis
            )

            suggest_iso_btn.click(
                fn=self.ui_controller.create_ubuntu_iso_download_suggestions,
                outputs=ubuntu_analysis
            )

            validate_btn.click(
                fn=self.ui_controller.validate_ipxe_script,
                inputs=[ipxe_script_output],
                outputs=ipxe_status
            )

            save_ipxe_btn.click(
                fn=self.ui_controller.save_ipxe_menu,
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
                    fn=self.ui_controller.add_custom_ipxe_entry,
                    inputs=[ipxe_script_output, entry_name, entry_title, entry_kernel,
                            entry_initrd, entry_cmdline, entry_description],
                    outputs=ipxe_script_output
                )

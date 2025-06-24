from app.ui_tabs.base_tab import PXEBootStationUI
from app.ui_tabs.helpers import safe_method, _create_action_buttons, _create_status_textbox
import gradio as gr

class TestingTab:
    def __init__(self, ui_controller: PXEBootStationUI):
        self.ui_controller = ui_controller

    def create_tab(self):
        with gr.Tab("🧪 System Testing"):
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
                    fn=self.ui_controller.run_full_system_test,
                    outputs=test_output
                )

                quick_test_btn.click(
                    fn=self.ui_controller.run_legacy_http_test,
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
                    fn=self.ui_controller.test_tftp_connection,
                    inputs=[tftp_host, tftp_port, tftp_file],
                    outputs=manual_test_output
                )

                http_test_btn.click(
                    fn=self.ui_controller.test_http_endpoint,
                    inputs=[http_url, http_timeout],
                    outputs=manual_test_output
                )

                file_test_btn.click(
                    fn=self.ui_controller.check_file_exists,
                    inputs=[file_path],
                    outputs=manual_test_output
                )

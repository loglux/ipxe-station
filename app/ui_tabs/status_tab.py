# app/ui_tabs/status_tab.py
from .base_tab import PXEBootStationUI
from .helpers import safe_method, _create_action_buttons, _create_status_textbox
import gradio as gr

class StatusTab:
    def __init__(self, ui_controller: PXEBootStationUI):
        self.ui_controller = ui_controller

    def create_tab(self):
        with gr.Tab("📊 System Status"):
            gr.Markdown("## 🖥️ System Status & Health Monitor")
            with gr.Row():
                refresh_btn, export_btn = _create_action_buttons(
                    ("Refresh Status", "primary", "🔄"),
                    ("Export JSON", "secondary", "📄")
                )

            status_output = _create_status_textbox(
                label="System Status",
                initial_value=self.ui_controller.get_system_status_display(),
                lines=25,
                max_lines=50,
                show_label=False
            )

            refresh_btn.click(
                fn=self.ui_controller.refresh_system_status,
                outputs=status_output
            )

            export_btn.click(
                fn=self.ui_controller.export_system_status,
                outputs=_create_status_textbox(label="JSON Export", lines=5)
            )

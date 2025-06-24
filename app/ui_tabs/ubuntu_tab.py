from app.ui_tabs.base_tab import PXEBootStationUI
from app.ui_tabs.helpers import safe_method, _create_action_buttons, _create_status_textbox
import gradio as gr


class UbuntuTab:
    def __init__(self, ui_controller: PXEBootStationUI):
        self.ui_controller = ui_controller

    def create_tab(self):
        with gr.Tab("🐧 Ubuntu Download"):
            gr.Markdown("## 🐧 Ubuntu Files Download & Management")

            with gr.Row():
                with gr.Column():
                    summary_output = _create_status_textbox(
                        label="Ubuntu Versions Summary",
                        initial_value=self.ui_controller.get_ubuntu_summary(),
                        lines=4
                    )
                    refresh_summary_btn = gr.Button("🔄 Refresh Summary", variant="secondary", size="sm")

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

            gr.Markdown("### 🔧 Manage Installed Versions")
            with gr.Row():
                with gr.Column():
                    installed_versions = gr.Dropdown(
                        choices=self.ui_controller.get_installed_ubuntu_versions(),
                        value=self.ui_controller.get_installed_ubuntu_versions()[0] if self.ui_controller.get_installed_ubuntu_versions() and
                                                                                   self.ui_controller.get_installed_ubuntu_versions()[
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

            download_btn.click(
                fn=self.ui_controller.download_ubuntu_files,
                inputs=[ubuntu_version],
                outputs=download_status,
                show_progress=True
            )

            check_all_btn.click(
                fn=self.ui_controller.check_ubuntu_files,
                outputs=download_status
            )

            check_version_btn.click(
                fn=self.ui_controller.check_specific_ubuntu_version,
                inputs=[installed_versions],
                outputs=management_status
            )

            refresh_versions_btn.click(
                fn=self.ui_controller.refresh_ubuntu_versions_dropdown,
                outputs=installed_versions
            )

            delete_version_btn.click(
                fn=self.ui_controller.delete_ubuntu_version,
                inputs=[installed_versions],
                outputs=management_status
            ).then(
                fn=self.ui_controller.refresh_ubuntu_versions_dropdown,
                outputs=installed_versions
            ).then(
                fn=self.ui_controller.get_ubuntu_summary,
                outputs=summary_output
            )

            delete_all_btn.click(
                fn=self.ui_controller.delete_all_ubuntu_versions,
                outputs=management_status
            ).then(
                fn=self.ui_controller.refresh_ubuntu_versions_dropdown,
                outputs=installed_versions
            ).then(
                fn=self.ui_controller.get_ubuntu_summary,
                outputs=summary_output
            )

            refresh_summary_btn.click(
                fn=self.ui_controller.get_ubuntu_summary,
                outputs=summary_output
            )

from app.ui_tabs.base_tab import PXEBootStationUI
import gradio as gr
from app.ui_tabs.helpers import safe_method, _create_action_buttons, _create_status_textbox

class ISOTab:
    def __init__(self, ui_controller: PXEBootStationUI):
        self.ui_controller = ui_controller

    def create_tab(self):
        with gr.Tab("📁 ISO Management"):
            gr.Markdown("## 📁 ISO Images Download & Management")

            with gr.Row():
                with gr.Column():
                    iso_summary_output = _create_status_textbox(
                        label="ISO Images Summary",
                        initial_value=self.ui_controller.get_iso_summary(),
                        lines=5
                    )
                    refresh_iso_summary_btn = gr.Button("🔄 Refresh Summary", variant="secondary", size="sm")

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
                            choices=list(self.ui_controller.iso_manager.get_categories().keys()) if self.ui_controller.iso_manager else [
                                "custom"],
                            value="custom",
                            label="Category",
                            scale=1
                        )

                    with gr.Accordion("📦 Boot File Extraction Options", open=False):
                        with gr.Row():
                            extract_files_download = gr.Checkbox(
                                label="Extract boot files from ISO",
                                value=False,
                                info="Extract kernel, initrd, and config files for fast booting"
                            )

                        with gr.Row():
                            iso_retention_download = gr.Dropdown(
                                choices=self.ui_controller.get_iso_retention_options(),
                                value="keep",
                                label="ISO file handling after extraction",
                                visible=False
                            )

                    download_iso_btn = gr.Button("⬇️ Download ISO", variant="primary")

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
                            choices=list(self.ui_controller.iso_manager.get_categories().keys()) if self.ui_controller.iso_manager else [
                                "custom"],
                            value="custom",
                            label="Category",
                            scale=1
                        )

                    with gr.Accordion("📦 Boot File Extraction Options", open=False):
                        with gr.Row():
                            extract_files_upload = gr.Checkbox(
                                label="Extract boot files from ISO",
                                value=False,
                                info="Extract kernel, initrd, and config files for fast booting"
                            )

                        with gr.Row():
                            iso_retention_upload = gr.Dropdown(
                                choices=self.ui_controller.get_iso_retention_options(),
                                value="keep",
                                label="ISO file handling after extraction",
                                visible=False
                            )

                    upload_iso_btn = gr.Button("📤 Upload ISO", variant="primary")

            iso_operation_status = _create_status_textbox(
                label="Operation Status",
                lines=12
            )

            gr.Markdown("### 🔧 Manage Existing ISOs")
            with gr.Row():
                with gr.Column():
                    initial_folders = self.ui_controller.get_iso_folder_names()

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

            download_iso_btn.click(
                fn=self.ui_controller.download_iso_from_url,
                inputs=[iso_url, iso_folder_name, iso_display_name, iso_category,
                        extract_files_download, iso_retention_download],
                outputs=iso_operation_status,
                show_progress=True
            )

            upload_iso_btn.click(
                fn=self.ui_controller.upload_iso_file,
                inputs=[iso_file_upload, upload_folder_name, upload_display_name, upload_category,
                        extract_files_upload, iso_retention_upload],
                outputs=iso_operation_status
            )

            check_iso_btn.click(
                fn=self.ui_controller.get_iso_status,
                inputs=[existing_isos],
                outputs=iso_management_status
            )

            check_all_isos_btn.click(
                fn=lambda: self.ui_controller.get_iso_status(),
                outputs=iso_management_status
            )

            refresh_iso_list_btn.click(
                fn=self.ui_controller.refresh_iso_list,
                outputs=existing_isos
            )

            delete_iso_btn.click(
                fn=self.ui_controller.delete_iso,
                inputs=[existing_isos],
                outputs=iso_management_status
            ).then(
                fn=self.ui_controller.refresh_iso_list,
                outputs=existing_isos
            ).then(
                fn=self.ui_controller.get_iso_summary,
                outputs=iso_summary_output
            )

            refresh_iso_summary_btn.click(
                fn=self.ui_controller.get_iso_summary,
                outputs=iso_summary_output
            )

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

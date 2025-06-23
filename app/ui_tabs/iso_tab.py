"""
ISO Management Tab for PXE Boot Station UI
Handles ISO images download, upload, and management with boot file extraction
"""

import gradio as gr
from typing import Optional, List

from .base_tab import BaseTab
from .helpers import safe_method


class ISOTab(BaseTab):
    """ISO Images Download & Management tab."""

    @property
    def tab_name(self) -> str:
        return "📁 ISO Management"

    @property
    def tab_id(self) -> str:
        return "iso-tab"

    def create_tab(self) -> gr.Tab:
        """Create the ISO Management tab."""
        with gr.Tab(self.tab_name, elem_id=self.tab_id) as tab:
            # Tab header
            self._create_section_header(
                "ISO Images Download & Management",
                icon="📁",
                description="Download, upload, and manage ISO images with boot file extraction"
            )

            # Summary section
            self._create_iso_summary_section()

            # Download from URL section
            self._create_download_url_section()

            # Upload file section
            self._create_upload_file_section()

            # Management section
            self._create_iso_management_section()

            # Help section
            self._create_help_section()

            # Setup event handlers
            self._setup_event_handlers()

        return tab

    def _create_iso_summary_section(self):
        """Create ISO images summary section."""
        with gr.Row():
            with gr.Column():
                self.iso_summary_output, self.refresh_iso_summary_btn = self._create_summary_ui_section(
                    get_summary_fn=self._get_iso_summary,
                    title="ISO Images Summary",
                    icon="📊"
                )

    def _create_download_url_section(self):
        """Create download from URL section."""
        self._create_section_header("Download ISO from URL", icon="🌐")

        with gr.Row():
            with gr.Column():
                self.iso_url = gr.Textbox(
                    label="ISO Download URL",
                    placeholder="https://example.com/my-disk.iso",
                    lines=1,
                    info="URL of the ISO file to download"
                )

                with gr.Row():
                    self.iso_folder_name = gr.Textbox(
                        label="Folder Name",
                        placeholder="my-rescue-disk",
                        scale=2,
                        info="Unique folder name for this ISO"
                    )
                    self.iso_display_name = gr.Textbox(
                        label="Display Name",
                        placeholder="My Rescue Disk",
                        scale=2,
                        info="Human-readable name"
                    )
                    self.iso_category = gr.Dropdown(
                        choices=self._get_iso_categories(),
                        value="custom",
                        label="Category",
                        scale=1,
                        info="ISO category"
                    )

                # Extraction options for download
                self._create_extraction_options_section("download")

                self.download_iso_btn = gr.Button("⬇️ Download ISO", variant="primary")

    def _create_upload_file_section(self):
        """Create upload file section."""
        self._create_section_header("Upload ISO File", icon="📤")

        with gr.Row():
            with gr.Column():
                self.iso_file_upload = gr.File(
                    label="Select ISO File",
                    file_types=[".iso"],
                    file_count="single",
                    # info="Select ISO file from your computer"
                )

                with gr.Row():
                    self.upload_folder_name = gr.Textbox(
                        label="Folder Name",
                        placeholder="my-utility",
                        scale=2,
                        info="Unique folder name for this ISO"
                    )
                    self.upload_display_name = gr.Textbox(
                        label="Display Name",
                        placeholder="My Utility Disk",
                        scale=2,
                        info="Human-readable name"
                    )
                    self.upload_category = gr.Dropdown(
                        choices=self._get_iso_categories(),
                        value="custom",
                        label="Category",
                        scale=1,
                        info="ISO category"
                    )

                # Extraction options for upload
                self._create_extraction_options_section("upload")

                self.upload_iso_btn = gr.Button("📤 Upload ISO", variant="primary")

        # Status output for downloads/uploads
        self.iso_operation_status = self._create_status_textbox(
            label="Operation Status",
            lines=12,
            component_key="iso_operation_status"
        )

    def _create_extraction_options_section(self, prefix: str):
        """Create extraction options section."""
        with gr.Accordion("📦 Boot File Extraction Options", open=False):
            extract_files_attr = f"extract_files_{prefix}"
            iso_retention_attr = f"iso_retention_{prefix}"

            with gr.Row():
                extract_checkbox = gr.Checkbox(
                    label="Extract boot files from ISO",
                    value=False,
                    info="Extract kernel, initrd, and config files for fast booting"
                )
                setattr(self, extract_files_attr, extract_checkbox)

            with gr.Row():
                retention_dropdown = gr.Dropdown(
                    choices=self._get_iso_retention_options(),
                    value="keep",
                    label="ISO file handling after extraction",
                    visible=False,  # Will be shown when extract_files is checked
                    info="What to do with ISO file after extraction"
                )
                setattr(self, iso_retention_attr, retention_dropdown)

            # Show/hide retention options based on extraction checkbox
            extract_checkbox.change(
                fn=lambda checked: gr.update(visible=checked),
                inputs=[extract_checkbox],
                outputs=[retention_dropdown]
            )

    def _create_iso_management_section(self):
        """Create management section for existing ISOs."""
        self._create_section_header("Manage Existing ISOs", icon="🔧")

        with gr.Row():
            with gr.Column():
                # Get initial folder list
                initial_folders = self._get_iso_folder_names()

                self.existing_isos = gr.Dropdown(
                    choices=initial_folders,
                    value=initial_folders[0] if initial_folders else "No ISOs found",
                    label="Existing ISOs",
                    allow_custom_value=False,
                    info="Select ISO to manage"
                )

                with gr.Row():
                    self.check_iso_btn, self.refresh_iso_list_btn, self.delete_iso_btn = self._create_action_buttons(
                        ("Check ISO", "secondary", "🔍"),
                        ("Refresh List", "secondary", "🔄"),
                        ("Delete ISO", "stop", "🗑️"),
                        component_keys=["check_iso_btn", "refresh_iso_list_btn", "delete_iso_btn"]
                    )

                self.check_all_isos_btn = gr.Button("📋 Check All ISOs", variant="secondary")

        self.iso_management_status = self._create_status_textbox(
            label="Management Status",
            lines=10,
            component_key="iso_management_status"
        )

    def _create_help_section(self):
        """Create help section."""
        with gr.Accordion("ℹ️ Extraction Help", open=False):
            help_content = """
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
            """
            gr.Markdown(help_content)

    def _setup_event_handlers(self):
        """Setup all event handlers for the tab."""
        # Download from URL
        self.download_iso_btn.click(
            fn=self._download_iso_from_url,
            inputs=[
                self.iso_url, self.iso_folder_name, self.iso_display_name,
                self.iso_category, self.extract_files_download, self.iso_retention_download
            ],
            outputs=self.iso_operation_status,
            show_progress=True
        )

        # Upload file
        self.upload_iso_btn.click(
            fn=self._upload_iso_file,
            inputs=[
                self.iso_file_upload, self.upload_folder_name, self.upload_display_name,
                self.upload_category, self.extract_files_upload, self.iso_retention_upload
            ],
            outputs=self.iso_operation_status
        )

        # Management section events
        self.check_iso_btn.click(
            fn=self._get_iso_status,
            inputs=[self.existing_isos],
            outputs=self.iso_management_status
        )

        self.check_all_isos_btn.click(
            fn=lambda: self._get_iso_status(),
            outputs=self.iso_management_status
        )

        self.refresh_iso_list_btn.click(
            fn=self._refresh_iso_list,
            outputs=self.existing_isos
        )

        # Delete ISO with chain events
        self._chain_events(
            self.delete_iso_btn,
            [
                {
                    'fn': self._delete_iso,
                    'inputs': [self.existing_isos],
                    'outputs': [self.iso_management_status]
                },
                {
                    'fn': self._refresh_iso_list,
                    'outputs': [self.existing_isos]
                },
                {
                    'fn': self._get_iso_summary,
                    'outputs': [self.iso_summary_output]
                }
            ]
        )

        # Summary refresh
        self.refresh_iso_summary_btn.click(
            fn=self._get_iso_summary,
            outputs=self.iso_summary_output
        )

    # =========================
    # TAB-SPECIFIC METHODS
    # =========================

    @safe_method(module_attr='iso_manager', error_prefix='ISO download')
    def _download_iso_from_url(self, url: str, folder_name: str, display_name: str,
                               category: str = "custom", extract_files: bool = False,
                               iso_retention: str = "keep", progress=gr.Progress()) -> str:
        """Download ISO from URL with progress tracking and optional extraction."""
        if not self.ui_controller.iso_manager:
            return "❌ ISO manager module not available"

        # Validate inputs
        if not url or not url.strip():
            return "❌ ISO URL is required"

        if not folder_name or not folder_name.strip():
            return "❌ Folder name is required"

        if not display_name or not display_name.strip():
            return "❌ Display name is required"

        def progress_callback(current: int, total: int, filename: str):
            if total > 0:
                percent = (current / total) * 100
                progress(percent / 100, desc=f"Downloading {filename}")

        try:
            result = self.ui_controller.iso_manager.download_iso_from_url(
                url=url.strip(),
                folder_name=folder_name.strip(),
                display_name=display_name.strip(),
                category=category,
                extract_files=extract_files,
                iso_retention=iso_retention,
                progress_callback=progress_callback
            )
            return result
        except Exception as e:
            return f"❌ ISO download failed: {str(e)}"

    @safe_method(module_attr='iso_manager', error_prefix='ISO upload')
    def _upload_iso_file(self, file_obj, folder_name: str, display_name: str,
                         category: str = "custom", extract_files: bool = False,
                         iso_retention: str = "keep") -> str:
        """Upload ISO file from local system with optional extraction."""
        if not self.ui_controller.iso_manager:
            return "❌ ISO manager module not available"

        if not file_obj:
            return "❌ No file selected for upload"

        # Validate inputs
        if not folder_name or not folder_name.strip():
            return "❌ Folder name is required"

        if not display_name or not display_name.strip():
            return "❌ Display name is required"

        try:
            result = self.ui_controller.iso_manager.upload_iso_file(
                file_obj=file_obj,
                folder_name=folder_name.strip(),
                display_name=display_name.strip(),
                category=category,
                extract_files=extract_files,
                iso_retention=iso_retention
            )
            return result
        except Exception as e:
            return f"❌ ISO upload failed: {str(e)}"

    def _get_iso_retention_options(self) -> List[str]:
        """Get ISO retention options for dropdown."""
        if not self.ui_controller.iso_manager:
            return ["keep"]

        try:
            options = self.ui_controller.iso_manager.get_iso_retention_options()
            return list(options.keys())
        except Exception:
            return ["keep", "subfolder", "delete"]

    def _get_iso_categories(self) -> List[str]:
        """Get available ISO categories."""
        if not self.ui_controller.iso_manager:
            return ["custom"]

        try:
            categories = self.ui_controller.iso_manager.get_categories()
            return list(categories.keys())
        except Exception:
            return ["antivirus", "utilities", "recovery", "linux", "windows", "custom"]

    def _get_iso_folder_names(self) -> List[str]:
        """Get list of existing ISO folder names for dropdowns."""
        if not self.ui_controller.iso_manager:
            return ["No ISOs found"]

        try:
            isos = self.ui_controller.iso_manager.list_existing_isos()
            if not isos:
                return ["No ISOs found"]

            folders = [iso["folder_name"] for iso in isos]
            return sorted(folders)
        except Exception:
            return ["Error loading ISOs"]

    def _refresh_iso_list(self) -> dict:
        """Refresh ISO dropdown list."""
        try:
            folders = self._get_iso_folder_names()
            value = folders[0] if folders else "No ISOs found"
            return gr.update(choices=folders, value=value)
        except Exception:
            return gr.update(choices=["Error loading ISOs"], value="Error loading ISOs")

    @safe_method(module_attr='iso_manager', error_prefix='ISO status check')
    def _get_iso_status(self, folder_name: str = None) -> str:
        """Get detailed status of ISOs."""
        if not self.ui_controller.iso_manager:
            return "❌ ISO manager module not available"

        try:
            if folder_name and folder_name not in ["No ISOs found", "Error loading ISOs"]:
                return self.ui_controller.iso_manager.get_iso_status(folder_name)
            elif folder_name in ["No ISOs found", "Error loading ISOs"]:
                return "❌ Please select a valid ISO to check"
            else:
                return self.ui_controller.iso_manager.get_iso_status()
        except Exception as e:
            return f"❌ ISO status check failed: {str(e)}"

    @safe_method(module_attr='iso_manager', error_prefix='ISO deletion')
    def _delete_iso(self, folder_name: str) -> str:
        """Delete ISO and its directory."""
        if not self.ui_controller.iso_manager:
            return "❌ ISO manager module not available"

        if folder_name in ["No ISOs found", "Error loading ISOs"]:
            return "❌ Please select a valid ISO to delete"

        try:
            return self.ui_controller.iso_manager.delete_iso(folder_name)
        except Exception as e:
            return f"❌ ISO deletion failed: {str(e)}"

    @safe_method(module_attr='iso_manager', error_prefix='ISO summary')
    def _get_iso_summary(self) -> str:
        """Get brief summary of ISO management for UI."""
        if not self.ui_controller.iso_manager:
            return "❌ ISO manager module not available"

        try:
            return self.ui_controller.iso_manager.get_summary()
        except Exception as e:
            return f"❌ Error getting ISO summary: {str(e)}"

    # =========================
    # ADDITIONAL FEATURES
    # =========================

    def get_iso_recommendations(self) -> str:
        """Get recommendations for useful ISOs to download."""
        recommendations = []
        recommendations.append("💡 **Recommended ISOs for PXE Boot**")
        recommendations.append("=" * 45)

        # Rescue and recovery tools
        recommendations.append("\n🔧 **Rescue & Recovery Tools:**")
        recommendations.append("   • **SystemRescue** - Linux rescue toolkit")
        recommendations.append("     URL: https://osdn.net/projects/systemrescuecd/")
        recommendations.append("   • **Clonezilla Live** - Disk cloning and imaging")
        recommendations.append("     URL: https://clonezilla.org/downloads/")
        recommendations.append("   • **GParted Live** - Partition editor")
        recommendations.append("     URL: https://gparted.org/download.php")

        # Security tools
        recommendations.append("\n🛡️ **Security & Antivirus:**")
        recommendations.append("   • **Kali Linux Live** - Penetration testing")
        recommendations.append("     URL: https://www.kali.org/get-kali/")
        recommendations.append("   • **Kaspersky Rescue Disk** - Antivirus rescue")
        recommendations.append("     URL: https://www.kaspersky.com/downloads/thank-you/free-rescue-disk")

        # Utilities
        recommendations.append("\n🛠️ **System Utilities:**")
        recommendations.append("   • **Memtest86+** - Memory testing")
        recommendations.append("     URL: https://www.memtest.org/")
        recommendations.append("   • **Ultimate Boot CD** - Hardware diagnostics")
        recommendations.append("     URL: http://www.ultimatebootcd.com/")

        # Linux distributions
        recommendations.append("\n🐧 **Linux Distributions:**")
        recommendations.append("   • **Ubuntu Live** - Full Ubuntu desktop")
        recommendations.append("     URL: https://ubuntu.com/download/desktop")
        recommendations.append("   • **Debian Live** - Stable Linux distribution")
        recommendations.append("     URL: https://www.debian.org/CD/live/")

        recommendations.append("\n📦 **Extraction Tips:**")
        recommendations.append("   • Enable extraction for faster booting")
        recommendations.append("   • Keep ISOs for full functionality")
        recommendations.append("   • Use categories to organize your collection")

        return "\n".join(recommendations)

    def get_extraction_guide(self) -> str:
        """Get detailed guide on boot file extraction."""
        guide = []
        guide.append("📦 **Boot File Extraction Guide**")
        guide.append("=" * 40)

        guide.append("\n🎯 **What happens during extraction:**")
        guide.append("   1. ISO is mounted using 7-Zip")
        guide.append("   2. Boot files are located (vmlinuz, initrd, config)")
        guide.append("   3. Files are copied to the folder")
        guide.append("   4. ISO is handled according to retention policy")

        guide.append("\n⚡ **Benefits of extraction:**")
        guide.append("   • **Faster boot** - Direct kernel loading")
        guide.append("   • **Less network traffic** - No ISO transfer")
        guide.append("   • **More options** - Both fast and full boot modes")
        guide.append("   • **Better compatibility** - Works with more hardware")

        guide.append("\n🔍 **Common extracted files:**")
        guide.append("   • **vmlinuz** - Linux kernel")
        guide.append("   • **initrd** - Initial RAM disk")
        guide.append("   • **config.cfg** - Boot configuration")
        guide.append("   • **live/**, **casper/** - Live system directories")

        guide.append("\n💾 **Retention policies:**")
        guide.append("   • **Keep** - ISO + extracted files (most flexible)")
        guide.append("   • **Subfolder** - ISO moved to iso/ (organized)")
        guide.append("   • **Delete** - Only extracted files (space-efficient)")

        guide.append("\n🚀 **When to use each option:**")
        guide.append("   • **Fast boot**: When you need quick system access")
        guide.append("   • **Full boot**: When you need complete ISO functionality")
        guide.append("   • **Extraction**: For most rescue and utility disks")

        return "\n".join(guide)

    # =========================
    # TAB VALIDATION
    # =========================

    def validate_tab(self) -> Optional[str]:
        """
        Validate that this tab can function properly.

        Returns:
            Error message if validation fails, None if successful
        """
        return self._validate_required_modules(['iso_manager'])

    def get_debug_info(self) -> str:
        """Get debug information for this tab."""
        info = [
            f"Tab: {self.tab_name}",
            f"Components: {len(self._components)}",
            f"ISO Manager Available: {bool(self.ui_controller.iso_manager)}",
        ]

        if self.ui_controller.iso_manager:
            try:
                isos = self.ui_controller.iso_manager.list_existing_isos()
                categories = self.ui_controller.iso_manager.get_categories()
                info.append(f"Existing ISOs: {len(isos)}")
                info.append(f"Available Categories: {len(categories)}")
            except Exception as e:
                info.append(f"ISO Check Error: {str(e)}")

        validation_error = self.validate_tab()
        if validation_error:
            info.append(f"Validation Error: {validation_error}")
        else:
            info.append("Validation: ✅ Passed")

        return "\n".join(info)
"""
Ubuntu Download Tab for PXE Boot Station UI
Handles Ubuntu files download and management with multi-version support
"""

import gradio as gr
from typing import Optional, List

from .base_tab import BaseTab
from .helpers import safe_method


class UbuntuTab(BaseTab):
    """Ubuntu Files Download & Management tab."""

    @property
    def tab_name(self) -> str:
        return "🐧 Ubuntu Download"

    @property
    def tab_id(self) -> str:
        return "ubuntu-tab"

    def create_tab(self) -> gr.Tab:
        """Create the Ubuntu Download tab."""
        with gr.Tab(self.tab_name, elem_id=self.tab_id) as tab:
            # Tab header
            self._create_section_header(
                "Ubuntu Files Download & Management",
                icon="🐧",
                description="Download and manage multiple Ubuntu versions for PXE boot"
            )

            # Summary section
            self._create_ubuntu_summary_section()

            # Download section
            self._create_download_section()

            # Management section
            self._create_management_section()

            # Setup event handlers
            self._setup_event_handlers()

        return tab

    def _create_ubuntu_summary_section(self):
        """Create Ubuntu versions summary section."""
        with gr.Row():
            with gr.Column():
                # Create summary textbox manually since base method returns 3 elements
                self.summary_output = self._create_status_textbox(
                    label="Ubuntu Versions Summary",
                    initial_value=self._get_ubuntu_summary(),
                    lines=4,
                    component_key="summary_output"
                )
                self.refresh_summary_btn = gr.Button("🔄 Refresh Summary", variant="secondary", size="sm")

    def _create_download_section(self):
        """Create download new version section."""
        self._create_section_header("Download New Version", icon="📥")

        with gr.Row():
            with gr.Column():
                self.ubuntu_version = gr.Dropdown(
                    choices=["24.04", "22.04", "20.04"],
                    value="24.04",
                    label="Ubuntu Version to Download",
                    info="Select Ubuntu LTS version to download"
                )

                with gr.Row():
                    self.download_btn, self.check_all_btn = self._create_action_buttons(
                        ("Download Ubuntu Files", "primary", "⬇️"),
                        ("Check All Versions", "secondary", "🔍"),
                        component_keys=["download_btn", "check_all_btn"]
                    )

        self.download_status = self._create_status_textbox(
            label="Download Status",
            lines=12,
            component_key="download_status"
        )

    def _create_management_section(self):
        """Create management section for installed versions."""
        self._create_section_header("Manage Installed Versions", icon="🔧")

        with gr.Row():
            with gr.Column():
                self.installed_versions = gr.Dropdown(
                    choices=self._get_installed_ubuntu_versions(),
                    value=self._get_default_version(),
                    label="Installed Versions",
                    allow_custom_value=False,
                    info="Select version to manage"
                )

                with gr.Row():
                    self.check_version_btn, self.refresh_versions_btn, self.delete_version_btn = self._create_action_buttons(
                        ("Check Version", "secondary", "🔍"),
                        ("Refresh List", "secondary", "🔄"),
                        ("Delete Version", "stop", "🗑️"),
                        component_keys=["check_version_btn", "refresh_versions_btn", "delete_version_btn"]
                    )

                self.delete_all_btn = gr.Button("🗑️ Delete All Versions", variant="stop")

        self.management_status = self._create_status_textbox(
            label="Management Status",
            lines=8,
            component_key="management_status"
        )

    def _setup_event_handlers(self):
        """Setup all event handlers for the tab."""
        # Download section events
        self.download_btn.click(
            fn=self._download_ubuntu_files,
            inputs=[self.ubuntu_version],
            outputs=self.download_status,
            show_progress=True
        )

        self.check_all_btn.click(
            fn=self._check_ubuntu_files,
            outputs=self.download_status
        )

        # Management section events
        self.check_version_btn.click(
            fn=self._check_specific_ubuntu_version,
            inputs=[self.installed_versions],
            outputs=self.management_status
        )

        self.refresh_versions_btn.click(
            fn=self._refresh_ubuntu_versions_dropdown,
            outputs=self.installed_versions
        )

        # Delete version with chain events
        self._chain_events(
            self.delete_version_btn,
            [
                {
                    'fn': self._delete_ubuntu_version,
                    'inputs': [self.installed_versions],
                    'outputs': [self.management_status]
                },
                {
                    'fn': self._refresh_ubuntu_versions_dropdown,
                    'outputs': [self.installed_versions]
                },
                {
                    'fn': self._get_ubuntu_summary,
                    'outputs': [self.summary_output]
                }
            ]
        )

        # Delete all versions with chain events
        self._chain_events(
            self.delete_all_btn,
            [
                {
                    'fn': self._delete_all_ubuntu_versions,
                    'outputs': [self.management_status]
                },
                {
                    'fn': self._refresh_ubuntu_versions_dropdown,
                    'outputs': [self.installed_versions]
                },
                {
                    'fn': self._get_ubuntu_summary,
                    'outputs': [self.summary_output]
                }
            ]
        )

        # Summary refresh
        self.refresh_summary_btn.click(
            fn=self._get_ubuntu_summary,
            outputs=self.summary_output
        )

    # =========================
    # TAB-SPECIFIC METHODS
    # =========================

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu download')
    def _download_ubuntu_files(self, version: str = "22.04", progress=gr.Progress()) -> str:
        """Download Ubuntu files with progress tracking."""
        if not self.ui_controller.ubuntu_downloader:
            return "❌ Ubuntu downloader module not available"

        # Validate version
        supported_versions = self.ui_controller.ubuntu_downloader.get_supported_versions()
        if version not in supported_versions:
            return f"❌ Unsupported version: {version}. Supported: {', '.join(supported_versions.keys())}"

        def progress_callback(current: int, total: int, filename: str):
            if total > 0:
                percent = (current / total) * 100
                progress(percent / 100, desc=f"Downloading {filename}")

        try:
            result = self.ui_controller.ubuntu_downloader.download_all_files(
                version=version,
                progress_callback=progress_callback
            )
            return result
        except Exception as e:
            return f"❌ Download failed: {str(e)}"

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu files check')
    def _check_ubuntu_files(self) -> str:
        """Check all Ubuntu files status."""
        if not self.ui_controller.ubuntu_downloader:
            return "❌ Ubuntu downloader module not available"

        return self.ui_controller.ubuntu_downloader.check_files_status()

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu version check')
    def _check_specific_ubuntu_version(self, version: str) -> str:
        """Check files for specific Ubuntu version."""
        if not self.ui_controller.ubuntu_downloader:
            return "❌ Ubuntu downloader module not available"

        if not version or version in ["No versions installed", "Error"]:
            return "❌ Please select a valid version to check"

        return self.ui_controller.ubuntu_downloader.check_files_status(version)

    def _get_installed_ubuntu_versions(self) -> List[str]:
        """Get list of installed Ubuntu versions for dropdown."""
        if not self.ui_controller.ubuntu_downloader:
            return ["No versions found"]

        try:
            installed = self.ui_controller.ubuntu_downloader.get_installed_versions()
            return installed if installed else ["No versions installed"]
        except Exception:
            return ["Error loading versions"]

    def _get_default_version(self) -> str:
        """Get default version for dropdown."""
        versions = self._get_installed_ubuntu_versions()
        if versions and versions[0] not in ["No versions installed", "No versions found", "Error loading versions"]:
            return versions[0]
        return "No versions installed"

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu version deletion')
    def _delete_ubuntu_version(self, version: str) -> str:
        """Delete specific Ubuntu version."""
        if not self.ui_controller.ubuntu_downloader:
            return "❌ Ubuntu downloader module not available"

        if not version or version in ["No versions installed", "Error", "No versions found"]:
            return "❌ Please select a valid version to delete"

        return self.ui_controller.ubuntu_downloader.delete_version(version)

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu versions deletion')
    def _delete_all_ubuntu_versions(self) -> str:
        """Delete all Ubuntu versions."""
        if not self.ui_controller.ubuntu_downloader:
            return "❌ Ubuntu downloader module not available"

        return self.ui_controller.ubuntu_downloader.delete_all_versions()

    def _refresh_ubuntu_versions_dropdown(self) -> dict:
        """Refresh the installed versions dropdown."""
        try:
            versions = self._get_installed_ubuntu_versions()
            value = versions[0] if versions else "No versions installed"
            return gr.update(choices=versions, value=value)
        except Exception:
            return gr.update(choices=["Error loading versions"], value="Error loading versions")

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu summary')
    def _get_ubuntu_summary(self) -> str:
        """Get Ubuntu installations summary."""
        if not self.ui_controller.ubuntu_downloader:
            return "❌ Ubuntu downloader module not available"

        try:
            installed = self.ui_controller.ubuntu_downloader.get_installed_versions()
            supported = list(self.ui_controller.ubuntu_downloader.get_supported_versions().keys())

            summary = []
            summary.append("📊 **Ubuntu Versions Overview**")
            summary.append(f"📁 Installed: {len(installed)} versions")
            summary.append(f"🔢 Available: {len(supported)} versions")

            if installed:
                summary.append(f"✅ Installed versions: {', '.join(installed)}")
            else:
                summary.append("ℹ️ No versions installed yet")

            summary.append(f"📥 Available to download: {', '.join(supported)}")

            # Add disk usage info if possible
            try:
                total_size = 0
                for version in installed:
                    ubuntu_dir = self.ui_controller.ubuntu_downloader.get_ubuntu_dir(version)
                    if ubuntu_dir.exists():
                        from app.backend.utils import calculate_total_size, format_file_size
                        version_size = calculate_total_size(ubuntu_dir)
                        total_size += version_size

                if total_size > 0:
                    total_size_human = format_file_size(total_size)
                    summary.append(f"💾 Total disk usage: {total_size_human}")

            except Exception:
                # Silently ignore disk usage calculation errors
                pass

            return "\n".join(summary)
        except Exception as e:
            return f"❌ Error getting summary: {str(e)}"

    # =========================
    # ADVANCED FEATURES
    # =========================

    @safe_method(module_attr='ubuntu_downloader', error_prefix='Ubuntu capabilities')
    def get_ubuntu_capabilities_overview(self) -> str:
        """Get overview of Ubuntu capabilities for each version."""
        if not self.ui_controller.ubuntu_downloader:
            return "❌ Ubuntu downloader module not available"

        try:
            installed = self.ui_controller.ubuntu_downloader.get_installed_versions()

            if not installed:
                return "📁 No Ubuntu versions installed\n\n🔍 Available versions to install: 24.04, 22.04, 20.04"

            overview = []
            overview.append("🐧 **Ubuntu Capabilities Overview**")
            overview.append("=" * 45)

            for version in installed:
                overview.append(f"\n📦 **Ubuntu {version} LTS**")

                # Get version info
                version_info = self.ui_controller.ubuntu_downloader.get_version_info(version)

                if version_info:
                    overview.append(f"   📁 Path: {version_info['install_path']}")
                    overview.append(f"   📥 Method: {version_info.get('method', 'unknown')}")
                    overview.append(f"   💾 Size: ~{version_info.get('size_mb', 0)} MB")
                    overview.append(f"   ✅ Installed: {version_info.get('installed', False)}")

                # Check file status
                status_result = self.ui_controller.ubuntu_downloader.check_files_status(version)
                if "✅" in status_result:
                    overview.append(f"   🚀 Status: Ready for PXE boot")
                else:
                    overview.append(f"   ⚠️ Status: Incomplete installation")

            overview.append(f"\n💡 **Recommendations:**")
            overview.append(f"   • Use 'Create Smart Menu' in iPXE tab to generate boot menu")
            overview.append(f"   • Check ISO Management tab for live boot options")
            overview.append(f"   • Each version provides netboot and rescue modes")

            return "\n".join(overview)

        except Exception as e:
            return f"❌ Error getting capabilities: {str(e)}"

    def get_version_comparison(self) -> str:
        """Get comparison of different Ubuntu versions."""
        comparison = []
        comparison.append("🔍 **Ubuntu Version Comparison**")
        comparison.append("=" * 40)

        versions_info = {
            "24.04": {
                "name": "Noble Numbat",
                "release": "April 2024",
                "support": "April 2029",
                "features": ["Latest kernel", "New installer", "Enhanced security"],
                "size": "~2.8GB ISO"
            },
            "22.04": {
                "name": "Jammy Jellyfish",
                "release": "April 2022",
                "support": "April 2027",
                "features": ["Stable kernel", "Proven reliability", "Wide hardware support"],
                "size": "~2.4GB ISO"
            },
            "20.04": {
                "name": "Focal Fossa",
                "release": "April 2020",
                "support": "April 2025",
                "features": ["Legacy compatibility", "Netboot support", "Smaller footprint"],
                "size": "~35MB netboot"
            }
        }

        for version, info in versions_info.items():
            comparison.append(f"\n🐧 **Ubuntu {version} LTS ({info['name']})**")
            comparison.append(f"   📅 Released: {info['release']}")
            comparison.append(f"   🛡️ Support until: {info['support']}")
            comparison.append(f"   📦 Download size: {info['size']}")
            comparison.append(f"   ✨ Key features:")
            for feature in info['features']:
                comparison.append(f"      • {feature}")

        comparison.append(f"\n💡 **Selection Guide:**")
        comparison.append(f"   • **24.04**: Latest features, newest hardware")
        comparison.append(f"   • **22.04**: Best balance of stability and features")
        comparison.append(f"   • **20.04**: Legacy systems, minimal bandwidth")

        return "\n".join(comparison)

    # =========================
    # TAB VALIDATION
    # =========================

    def validate_tab(self) -> Optional[str]:
        """
        Validate that this tab can function properly.

        Returns:
            Error message if validation fails, None if successful
        """
        return self._validate_required_modules(['ubuntu_downloader'])

    def get_debug_info(self) -> str:
        """Get debug information for this tab."""
        info = [
            f"Tab: {self.tab_name}",
            f"Components: {len(self._components)}",
            f"Ubuntu Downloader Available: {bool(self.ui_controller.ubuntu_downloader)}",
        ]

        if self.ui_controller.ubuntu_downloader:
            try:
                installed = self.ui_controller.ubuntu_downloader.get_installed_versions()
                supported = list(self.ui_controller.ubuntu_downloader.get_supported_versions().keys())
                info.append(f"Installed Versions: {len(installed)}")
                info.append(f"Supported Versions: {len(supported)}")

                if installed:
                    info.append(f"Versions: {', '.join(installed)}")
            except Exception as e:
                info.append(f"Version Check Error: {str(e)}")

        validation_error = self.validate_tab()
        if validation_error:
            info.append(f"Validation Error: {validation_error}")
        else:
            info.append("Validation: ✅ Passed")

        return "\n".join(info)
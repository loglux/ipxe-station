"""
Gradio Web UI for PXE Boot Station - Refactored with modular tabs
Main UI builder that assembles tabs from separate modules
"""

import gradio as gr
import json
import os
from typing import Dict, List, Tuple, Optional, Any

# Import new modular components
from ui_helpers import create_main_header, create_main_footer, COMMON_CSS
from ui_tabs import StatusTab, get_available_tabs, validate_tab_dependencies

# Import legacy components (will be refactored later)
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
    from iso_manager import ISOManager
except ImportError:
    ISOManager = None

try:
    from file_utils import FileManager
except ImportError:
    FileManager = None


# === LEGACY UI HELPER FUNCTIONS (to be moved to ui_helpers gradually) ===

def _create_status_textbox(label="Status", lines=10, initial_value="", max_lines=None, show_label=True, **kwargs):
    """Legacy status textbox function."""
    return gr.Textbox(
        label=label,
        value=initial_value,
        lines=lines,
        max_lines=max_lines,
        interactive=False,
        show_label=show_label,
        **kwargs
    )


def _create_action_buttons(*button_configs):
    """Legacy action buttons function."""
    buttons = []
    for config in button_configs:
        if len(config) == 3:
            text, variant, icon = config
            button_text = f"{icon} {text}" if icon else text
        elif len(config) == 2:
            text, variant = config
            button_text = text
        else:
            text = config[0]
            variant = "secondary"
            button_text = text

        btn = gr.Button(button_text, variant=variant)
        buttons.append(btn)

    return tuple(buttons) if len(buttons) > 1 else buttons[0]


class PXEBootStationUI:
    """Main UI controller class with multi-version Ubuntu support"""

    def __init__(self):
        # Initialize components with fallbacks
        self.system_tester = SystemTester() if SystemTester else None
        self.dhcp_manager = DHCPConfigManager() if DHCPConfigManager else None
        self.ipxe_manager = iPXEManager() if iPXEManager else None
        self.status_manager = SystemStatusManager() if SystemStatusManager else None
        self.ubuntu_downloader = UbuntuDownloader() if UbuntuDownloader else None
        self.file_manager = FileManager() if FileManager else None
        self.ipxe_templates = iPXETemplateManager() if iPXETemplateManager else None
        self.iso_manager = ISOManager() if ISOManager else None

    # === LEGACY METHODS (will be moved to tabs gradually) ===

    def _create_refresh_dropdown(self, get_func, empty_msg="No items found", error_msg="Error"):
        """Universal dropdown refresh method."""
        try:
            items = get_func()
            value = items[0] if items and items[0] != empty_msg else empty_msg
            return gr.update(choices=items, value=value)
        except Exception:
            return gr.update(choices=[error_msg], value=error_msg)

    # Note: Legacy methods will be gradually moved to appropriate tab classes
    # For now, keeping them here to maintain functionality during transition


def build_gradio_ui():
    """Build the main Gradio interface with new modular tab structure."""

    # Initialize UI controller
    ui_controller = PXEBootStationUI()

    # Validate tab dependencies
    tab_validation = validate_tab_dependencies(ui_controller)
    print("🔍 Tab validation results:")
    for tab_name, result in tab_validation.items():
        status = "✅" if result['available'] else "❌"
        print(f"  {status} {tab_name}: {result.get('error_message', 'OK')}")

    with gr.Blocks(
            title="🚀 PXE Boot Station",
            theme=gr.themes.Soft(),
            css=COMMON_CSS
    ) as demo:

        # Main header
        create_main_header()

        with gr.Tabs():
            # =========================
            # NEW MODULAR TABS
            # =========================

            # System Status Tab (NEW MODULAR APPROACH)
            StatusTab(ui_controller).create_tab()

            # =========================
            # LEGACY TABS (to be refactored)
            # =========================

            # System Testing Tab (LEGACY - to be moved to TestingTab)
            with gr.Tab("🧪 System Testing", elem_id="testing-tab"):
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

                    # Legacy event handlers
                    if ui_controller.system_tester:
                        full_test_btn.click(
                            fn=ui_controller.system_tester.run_full_system_test,
                            outputs=test_output
                        )

                    if legacy_test_http_endpoints:
                        quick_test_btn.click(
                            fn=legacy_test_http_endpoints,
                            outputs=test_output
                        )

            # DHCP Configuration Tab (LEGACY - to be moved to DHCPTab)
            with gr.Tab("🌐 DHCP Configuration", elem_id="dhcp-tab"):
                gr.Markdown("## 🌐 DHCP Server Configuration Generator")

                gr.HTML("<p><em>This tab will be refactored to DHCPTab module soon...</em></p>")

                # Placeholder content
                gr.Textbox(
                    label="DHCP Configuration",
                    value="DHCP configuration functionality will be moved to DHCPTab module",
                    lines=5,
                    interactive=False
                )

            # iPXE Menu Tab (LEGACY - to be moved to iPXETab)
            with gr.Tab("📋 iPXE Menu", elem_id="ipxe-tab"):
                gr.Markdown("## 📋 Enhanced iPXE Boot Menu Configuration")

                gr.HTML("<p><em>This tab will be refactored to iPXETab module soon...</em></p>")

                # Placeholder content
                gr.Textbox(
                    label="iPXE Menu",
                    value="iPXE menu functionality will be moved to iPXETab module",
                    lines=5,
                    interactive=False
                )

            # Ubuntu Download Tab (LEGACY - to be moved to UbuntuTab)
            with gr.Tab("🐧 Ubuntu Download", elem_id="ubuntu-tab"):
                gr.Markdown("## 🐧 Ubuntu Files Download & Management")

                gr.HTML("<p><em>This tab will be refactored to UbuntuTab module soon...</em></p>")

                # Placeholder content
                gr.Textbox(
                    label="Ubuntu Management",
                    value="Ubuntu download functionality will be moved to UbuntuTab module",
                    lines=5,
                    interactive=False
                )

            # ISO Management Tab (LEGACY - to be moved to ISOTab)
            with gr.Tab("📁 ISO Management", elem_id="iso-tab"):
                gr.Markdown("## 📁 ISO Images Download & Management")

                gr.HTML("<p><em>This tab will be refactored to ISOTab module soon...</em></p>")

                # Placeholder content
                gr.Textbox(
                    label="ISO Management",
                    value="ISO management functionality will be moved to ISOTab module",
                    lines=5,
                    interactive=False
                )

        # Main footer
        create_main_footer()

        # Debug information in development
        if os.getenv('DEBUG_UI'):
            with gr.Accordion("🔧 Debug Information", open=False):
                debug_info = []
                debug_info.append("📊 **Tab Validation Results:**")
                for tab_name, result in tab_validation.items():
                    status = "✅" if result['available'] else "❌"
                    debug_info.append(f"  {status} {tab_name}: {result.get('error_message', 'OK')}")

                debug_info.append(f"\n🏗️ **Available Tabs:** {len(get_available_tabs())}")
                debug_info.append(f"📦 **UI Controller Modules:**")
                for attr in ['system_tester', 'dhcp_manager', 'ipxe_manager', 'status_manager',
                             'ubuntu_downloader', 'iso_manager']:
                    status = "✅" if getattr(ui_controller, attr, None) else "❌"
                    debug_info.append(f"  {status} {attr}")

                gr.Markdown("\n".join(debug_info))

    return demo


# Create the demo instance
demo = build_gradio_ui()

if __name__ == "__main__":
    # Enable debug mode for development
    os.environ['DEBUG_UI'] = '1'

    demo.launch(
        server_name="0.0.0.0",
        server_port=9005,
        share=False,
        show_error=True,
        debug=False
    )
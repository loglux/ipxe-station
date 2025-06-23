"""
System Testing Tab for PXE Boot Station UI
Handles TFTP, HTTP, and system testing functionality
"""

import gradio as gr
from typing import Optional

from base_tab import BaseTab
from app.ui_helpers import safe_method


class TestingTab(BaseTab):
    """System & Network Testing tab."""

    @property
    def tab_name(self) -> str:
        return "🧪 System Testing"

    @property
    def tab_id(self) -> str:
        return "testing-tab"

    def create_tab(self) -> gr.Tab:
        """Create the System Testing tab."""
        with gr.Tab(self.tab_name, elem_id=self.tab_id) as tab:
            # Tab header
            self._create_section_header(
                "System & Network Testing",
                icon="🧪",
                description="Test TFTP, HTTP services and validate system components"
            )

            # Main testing section
            self._create_main_testing_section()

            # Manual testing tools (in accordion)
            self._create_manual_testing_section()

            # Setup event handlers
            self._setup_event_handlers()

        return tab

    def _create_main_testing_section(self):
        """Create the main testing section."""
        with gr.Column():
            # Action buttons
            with gr.Row():
                self.full_test_btn, self.quick_test_btn = self._create_action_buttons(
                    ("Run Full System Test", "primary", "🚀"),
                    ("Quick Network Test", "secondary", "⚡"),
                    component_keys=["full_test_btn", "quick_test_btn"]
                )

            # Test results output
            self.test_output = self._create_status_textbox(
                label="Test Results",
                lines=15,
                component_key="test_output"
            )

    def _create_manual_testing_section(self):
        """Create manual testing tools section."""
        with gr.Accordion("🔧 Manual Testing Tools", open=False):
            self._create_info_box(
                "Use these tools to test individual components manually.",
                box_type="info"
            )

            with gr.Row():
                # TFTP Test Column
                with gr.Column():
                    self._create_section_header("TFTP Test", icon="📡")
                    self.tftp_host = gr.Textbox(value="localhost", label="TFTP Host")
                    self.tftp_port = gr.Number(value=69, label="TFTP Port", precision=0)
                    self.tftp_file = gr.Textbox(value="undionly.kpxe", label="Test File")
                    self.tftp_test_btn = gr.Button("🧪 Test TFTP", variant="secondary")

                # HTTP Test Column
                with gr.Column():
                    self._create_section_header("HTTP Test", icon="🌐")
                    self.http_url = gr.Textbox(
                        value="http://localhost:8000/status",
                        label="HTTP URL"
                    )
                    self.http_timeout = gr.Number(value=5, label="Timeout (s)", precision=0)
                    self.http_test_btn = gr.Button("🧪 Test HTTP", variant="secondary")

                # File Check Column
                with gr.Column():
                    self._create_section_header("File Check", icon="📁")
                    self.file_path = gr.Textbox(
                        value="/srv/tftp/undionly.kpxe",
                        label="File Path"
                    )
                    self.file_test_btn = gr.Button("🧪 Check File", variant="secondary")

            # Manual test results
            self.manual_test_output = self._create_status_textbox(
                label="Manual Test Results",
                lines=5,
                component_key="manual_test_output"
            )

    def _setup_event_handlers(self):
        """Setup all event handlers for the tab."""
        # Main test buttons
        self.full_test_btn.click(
            fn=self._run_full_system_test,
            outputs=self.test_output
        )

        self.quick_test_btn.click(
            fn=self._run_quick_network_test,
            outputs=self.test_output
        )

        # Manual test buttons
        self.tftp_test_btn.click(
            fn=self._test_tftp_connection,
            inputs=[self.tftp_host, self.tftp_port, self.tftp_file],
            outputs=self.manual_test_output
        )

        self.http_test_btn.click(
            fn=self._test_http_endpoint,
            inputs=[self.http_url, self.http_timeout],
            outputs=self.manual_test_output
        )

        self.file_test_btn.click(
            fn=self._check_file_exists,
            inputs=[self.file_path],
            outputs=self.manual_test_output
        )

    # =========================
    # TAB-SPECIFIC METHODS
    # =========================

    @safe_method(module_attr='system_tester', error_prefix='System testing')
    def _run_full_system_test(self) -> str:
        """Run comprehensive system test."""
        if not self.ui_controller.system_tester:
            return "❌ System tester module not available"

        return self.ui_controller.system_tester.run_full_system_test()

    def _run_quick_network_test(self) -> str:
        """Run quick network test using legacy function."""
        try:
            # Try to import and use legacy test function
            from tests import test_http_endpoints as legacy_test_http_endpoints
            if legacy_test_http_endpoints:
                return legacy_test_http_endpoints()
            else:
                return "❌ Legacy HTTP test function not available"
        except ImportError:
            return "❌ Tests module not available"
        except Exception as e:
            return f"❌ Quick network test failed: {str(e)}"

    @safe_method(module_attr='system_tester', error_prefix='TFTP test')
    def _test_tftp_connection(self, host: str = "localhost", port: int = 69,
                              filename: str = "undionly.kpxe") -> str:
        """Test TFTP connection with custom parameters."""
        if not self.ui_controller.system_tester:
            return "❌ System tester module not available"

        # Validate inputs
        if not host or not filename:
            return "❌ Host and filename are required"

        if port < 1 or port > 65535:
            return "❌ Port must be between 1 and 65535"

        return self.ui_controller.system_tester.tftp_tester.test_tftp_connection(
            host, int(port), filename
        )

    @safe_method(module_attr='system_tester', error_prefix='HTTP test')
    def _test_http_endpoint(self, url: str = "http://localhost:8000/status",
                            timeout: int = 5) -> str:
        """Test HTTP endpoint."""
        if not self.ui_controller.system_tester:
            return "❌ System tester module not available"

        # Validate inputs
        if not url:
            return "❌ URL is required"

        if not url.startswith(('http://', 'https://')):
            return "❌ URL must start with http:// or https://"

        if timeout < 1 or timeout > 60:
            return "❌ Timeout must be between 1 and 60 seconds"

        return self.ui_controller.system_tester.http_tester.test_endpoint(url, int(timeout))

    @safe_method(module_attr='system_tester', error_prefix='File check')
    def _check_file_exists(self, filepath: str) -> str:
        """Check if file exists."""
        if not self.ui_controller.system_tester:
            return "❌ System tester module not available"

        # Validate input
        if not filepath:
            return "❌ File path is required"

        return self.ui_controller.system_tester.file_checker.check_file_exists(filepath)

    # =========================
    # TAB VALIDATION
    # =========================

    def validate_tab(self) -> Optional[str]:
        """
        Validate that this tab can function properly.

        Returns:
            Error message if validation fails, None if successful
        """
        return self._validate_required_modules(['system_tester'])

    # =========================
    # ADDITIONAL TESTING METHODS
    # =========================

    def _get_testing_summary(self) -> str:
        """Get summary of available testing capabilities."""
        summary = []
        summary.append("🧪 **Testing Capabilities**")
        summary.append("=" * 30)

        # Check system tester availability
        if self.ui_controller.system_tester:
            summary.append("✅ **System Tester:** Available")
            summary.append("   • Full system test")
            summary.append("   • TFTP connection test")
            summary.append("   • HTTP endpoint test")
            summary.append("   • File existence check")
        else:
            summary.append("❌ **System Tester:** Not available")

        # Check legacy test functions
        try:
            from tests import test_http_endpoints
            if test_http_endpoints:
                summary.append("✅ **Legacy HTTP Test:** Available")
            else:
                summary.append("❌ **Legacy HTTP Test:** Not available")
        except ImportError:
            summary.append("❌ **Legacy HTTP Test:** Module not found")

        summary.append("")
        summary.append("💡 **Usage Tips:**")
        summary.append("• Use 'Full System Test' for comprehensive checks")
        summary.append("• Use 'Quick Network Test' for fast HTTP validation")
        summary.append("• Use manual tools for specific component testing")
        summary.append("• Check file paths before running file tests")

        return "\n".join(summary)

    def get_debug_info(self) -> str:
        """Get debug information for this tab."""
        info = [
            f"Tab: {self.tab_name}",
            f"Components: {len(self._components)}",
            f"System Tester Available: {bool(self.ui_controller.system_tester)}",
        ]

        # Test legacy imports
        try:
            from tests import test_http_endpoints
            info.append(f"Legacy HTTP Test: {'✅' if test_http_endpoints else '❌'}")
        except ImportError:
            info.append("Legacy HTTP Test: ❌ Module not found")

        validation_error = self.validate_tab()
        if validation_error:
            info.append(f"Validation Error: {validation_error}")
        else:
            info.append("Validation: ✅ Passed")

        return "\n".join(info)
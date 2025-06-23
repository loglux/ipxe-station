"""
System Status Tab for PXE Boot Station UI
Displays system health, services status, and resource usage
"""

import gradio as gr
from typing import Optional

from base_tab import BaseTab
from ui_helpers import safe_method


class StatusTab(BaseTab):
    """System Status and Health Monitor tab."""

    @property
    def tab_name(self) -> str:
        return "📊 System Status"

    @property
    def tab_id(self) -> str:
        return "status-tab"

    def create_tab(self) -> gr.Tab:
        """Create the System Status tab."""
        with gr.Tab(self.tab_name, elem_id=self.tab_id) as tab:
            # Tab header
            self._create_section_header(
                "System Status & Health Monitor",
                icon="🖥️",
                description="Monitor system health, services, and resource usage"
            )

            # Action buttons section
            self._create_action_buttons_section()

            # Main status display section
            self._create_status_display_section()

            # Export section (in accordion)
            self._create_export_section()

            # Setup event handlers
            self._setup_event_handlers()

        return tab

    def _create_action_buttons_section(self):
        """Create the action buttons section."""
        with gr.Row():
            self.refresh_btn, self.export_btn = self._create_action_buttons(
                ("Refresh Status", "primary", "🔄"),
                ("Export JSON", "secondary", "📄"),
                component_keys=["refresh_btn", "export_btn"]
            )

    def _create_status_display_section(self):
        """Create the main status display section."""
        self.status_output = self._create_status_textbox(
            label="System Status",
            initial_value=self._get_initial_status(),
            lines=25,
            component_key="status_output"
        )
        # Remove label to make it cleaner
        self.status_output.show_label = False

    def _create_export_section(self):
        """Create the export section in an accordion."""
        with gr.Accordion("📄 Export Options", open=False):
            self._create_info_box(
                "Export system status as JSON for external monitoring or backup.",
                box_type="info"
            )

            self.export_output = self._create_status_textbox(
                label="JSON Export",
                lines=10,
                component_key="export_output"
            )

    def _setup_event_handlers(self):
        """Setup all event handlers for the tab."""
        # Refresh button
        self.refresh_btn.click(
            fn=self._refresh_system_status,
            outputs=self.status_output
        )

        # Export button
        self.export_btn.click(
            fn=self._export_system_status,
            outputs=self.export_output
        )

    # =========================
    # TAB-SPECIFIC METHODS
    # =========================

    def _get_initial_status(self) -> str:
        """Get initial system status for display."""
        try:
            return self._get_system_status_display()
        except Exception as e:
            return f"❌ Error loading initial system status: {str(e)}"

    @safe_method(module_attr='status_manager', error_prefix='System status')
    def _get_system_status_display(self) -> str:
        """Get formatted system status for display."""
        if not self.ui_controller.status_manager:
            return "❌ System status manager not available"

        status = self.ui_controller.status_manager.get_complete_status()

        output = []
        output.append("🖥️ **SYSTEM STATUS**")
        output.append("=" * 50)

        # System info
        sys_info = status['system']
        output.append(f"🏠 **Hostname:** {sys_info['hostname']}")
        output.append(f"💻 **Platform:** {sys_info['platform']} ({sys_info['architecture']})")
        output.append(f"⚡ **CPU:** {sys_info['cpu_count']} cores, {sys_info['cpu_percent']:.1f}% used")
        output.append(
            f"🧠 **Memory:** {sys_info['memory_available_gb']:.1f}GB free / {sys_info['memory_total_gb']:.1f}GB total ({sys_info['memory_percent']:.1f}% used)")
        output.append(f"⏰ **Uptime:** {sys_info['uptime']}")
        output.append("")

        # Services status
        output.append("🔧 **SERVICES STATUS**")
        output.append("-" * 30)
        for name, service in status['services'].items():
            status_icon = {
                'running': '✅',
                'stopped': '❌',
                'error': '🔥',
                'unknown': '❓'
            }.get(service['status'], '❓')

            output.append(f"{status_icon} **{service['description']}**")
            output.append(f"   Status: {service['status'].upper()}")
            if service['pid']:
                output.append(f"   PID: {service['pid']}")
            if service['port']:
                output.append(f"   Port: {service['port']}/{service['protocol'].upper()}")
            if service['uptime']:
                output.append(f"   Uptime: {service['uptime']}")
            if service['error_message']:
                output.append(f"   Info: {service['error_message']}")
            output.append("")

        # Disk usage
        output.append("💾 **DISK USAGE**")
        output.append("-" * 20)
        for disk in status['disk_usage']:
            output.append(f"📁 **{disk['path']}**")
            output.append(f"   Total: {disk['total_gb']:.1f}GB")
            output.append(f"   Used: {disk['used_gb']:.1f}GB ({disk['percent']:.1f}%)")
            output.append(f"   Free: {disk['free_gb']:.1f}GB")
            output.append("")

        # PXE files status
        output.append("📋 **PXE FILES STATUS**")
        output.append("-" * 25)
        for name, file_info in status['pxe_files'].items():
            status_icon = '✅' if file_info['exists'] else '❌'
            output.append(f"{status_icon} **{name}**")
            output.append(f"   Path: {file_info['path']}")
            if file_info['exists']:
                output.append(f"   Size: {file_info['size_human']}")
                if file_info['modified']:
                    output.append(f"   Modified: {file_info['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                output.append(f"   Status: Missing")
            output.append("")

        # Health score and recommendations
        output.append("🏥 **SYSTEM HEALTH**")
        output.append("-" * 20)
        health_score = status['health_score']
        health_emoji = '🟢' if health_score >= 80 else '🟡' if health_score >= 60 else '🔴'
        output.append(f"{health_emoji} **Overall Health Score: {health_score}/100**")
        output.append("")

        output.append("💡 **RECOMMENDATIONS**")
        output.append("-" * 20)
        for rec in status['recommendations']:
            output.append(f"• {rec}")

        return "\n".join(output)

    @safe_method(module_attr='status_manager', error_prefix='System status refresh')
    def _refresh_system_status(self) -> str:
        """Refresh system status."""
        return self._get_system_status_display()

    @safe_method(module_attr='status_manager', error_prefix='System status export')
    def _export_system_status(self) -> str:
        """Export system status as JSON."""
        if not self.ui_controller.status_manager:
            return "❌ System status manager not available"

        return self.ui_controller.status_manager.export_status_json()

    # =========================
    # TAB VALIDATION
    # =========================

    def validate_tab(self) -> Optional[str]:
        """
        Validate that this tab can function properly.

        Returns:
            Error message if validation fails, None if successful
        """
        return self._validate_required_modules(['status_manager'])

    # =========================
    # DEBUGGING HELPERS
    # =========================

    def get_debug_info(self) -> str:
        """Get debug information for this tab."""
        info = [
            f"Tab: {self.tab_name}",
            f"Components: {len(self._components)}",
            f"Status Manager Available: {bool(self.ui_controller.status_manager)}",
        ]

        validation_error = self.validate_tab()
        if validation_error:
            info.append(f"Validation Error: {validation_error}")
        else:
            info.append("Validation: ✅ Passed")

        return "\n".join(info)
"""
iPXE Menu Tab for PXE Boot Station UI
Handles iPXE menu configuration generation, validation, and management
"""
# Bear in mind, if relocate: from app.ipxe_manager import iPXEEntry, line 488

import gradio as gr
from typing import Optional

from base_tab import BaseTab
from helpers import safe_method


class iPXETab(BaseTab):
    """Enhanced iPXE Boot Menu Configuration tab."""

    @property
    def tab_name(self) -> str:
        return "📋 iPXE Menu"

    @property
    def tab_id(self) -> str:
        return "ipxe-tab"

    def create_tab(self) -> gr.Tab:
        """Create the iPXE Menu tab."""
        with gr.Tab(self.tab_name, elem_id=self.tab_id) as tab:
            # Tab header
            self._create_section_header(
                "Enhanced iPXE Boot Menu Configuration",
                icon="📋",
                description="Create and manage iPXE boot menus with multi-mode Ubuntu support"
            )

            # Smart menu generation section
            self._create_smart_menu_section()

            # Menu output and validation section
            self._create_menu_output_section()

            # Classic templates section
            self._create_classic_templates_section()

            # Custom entry section
            self._create_custom_entry_section()

            # Sample menu preview section
            self._create_sample_preview_section()

            # Setup event handlers
            self._setup_event_handlers()

        return tab

    def _create_smart_menu_section(self):
        """Create smart menu generation section."""
        with gr.Row():
            with gr.Column():
                self._create_section_header("Smart Menu Generation", icon="🎨")

                self.menu_type = gr.Dropdown(
                    choices=[
                        ("Multi-Mode Menu (All Options)", "multi"),
                        ("Quick Menu (Netboot Only)", "quick")
                    ],
                    value="multi",
                    label="Menu Type",
                    info="Choose between comprehensive multi-mode or simple netboot menu"
                )

                self.ipxe_server_ip = gr.Textbox(
                    value="192.168.1.10",
                    label="PXE Server IP",
                    info="IP address of this PXE server"
                )

                self.ipxe_port = gr.Number(
                    value=8000,
                    label="HTTP Port",
                    precision=0,
                    info="HTTP port for serving boot files"
                )

                with gr.Row():
                    self.create_smart_btn, self.analyze_btn, self.suggest_iso_btn = self._create_action_buttons(
                        ("Create Smart Menu", "primary", "🎨"),
                        ("Analyze Ubuntu Files", "secondary", "🔍"),
                        ("ISO Suggestions", "secondary", "💿"),
                        component_keys=["create_smart_btn", "analyze_btn", "suggest_iso_btn"]
                    )

        # Status and analysis displays
        with gr.Row():
            with gr.Column():
                self.ipxe_status = self._create_status_textbox(
                    label="Menu Status",
                    lines=8,
                    component_key="ipxe_status"
                )

            with gr.Column():
                self.ubuntu_analysis = self._create_status_textbox(
                    label="Ubuntu Analysis",
                    lines=8,
                    component_key="ubuntu_analysis"
                )

    def _create_menu_output_section(self):
        """Create menu output and validation section."""
        # iPXE script output
        self.ipxe_script_output = gr.Code(
            label="Generated iPXE Boot Script",
            language="shell",
            lines=25,
            interactive=True
        )
        self.store_component("ipxe_script_output", self.ipxe_script_output)

        with gr.Row():
            self.validate_btn, self.save_ipxe_btn = self._create_action_buttons(
                ("Validate Script", "secondary", "✅"),
                ("Save Menu", "primary", "💾"),
                component_keys=["validate_btn", "save_ipxe_btn"]
            )

    def _create_classic_templates_section(self):
        """Create classic templates section."""
        with gr.Accordion("🎨 Classic Templates", open=False):
            self._create_info_box(
                "Original template selection for backward compatibility.",
                box_type="info"
            )

            self._create_section_header("Original Template Selection", icon="📋")

            self.template_choice = gr.Dropdown(
                choices=["ubuntu", "diagnostic", "multi_os"],
                value="ubuntu",
                label="Classic Template",
                info="Pre-defined menu templates"
            )

            self.create_template_btn = gr.Button("🎨 Create from Classic Template", variant="secondary")

    def _create_custom_entry_section(self):
        """Create custom entry addition section."""
        with gr.Accordion("➕ Add Custom Entry", open=False):
            self._create_info_box(
                "Add custom boot entries to your iPXE menu.",
                box_type="info"
            )

            self._create_section_header("Add Custom Boot Entry", icon="➕")

            with gr.Row():
                with gr.Column():
                    self.entry_name = gr.Textbox(
                        label="Entry Name (ID)",
                        placeholder="my_custom_os",
                        info="Unique identifier for the entry"
                    )
                    self.entry_title = gr.Textbox(
                        label="Display Title",
                        placeholder="My Custom OS",
                        info="Title shown in the menu"
                    )
                    self.entry_description = gr.Textbox(
                        label="Description (optional)",
                        info="Optional description for the entry"
                    )

                with gr.Column():
                    self.entry_kernel = gr.Textbox(
                        label="Kernel Path",
                        placeholder="custom/vmlinuz",
                        info="Path to kernel file"
                    )
                    self.entry_initrd = gr.Textbox(
                        label="Initrd Path (optional)",
                        placeholder="custom/initrd",
                        info="Path to initrd file (optional)"
                    )
                    self.entry_cmdline = gr.Textbox(
                        label="Kernel Command Line",
                        placeholder="ip=dhcp root=/dev/nfs",
                        info="Kernel boot parameters"
                    )

            self.add_entry_btn = gr.Button("➕ Add Entry to Menu", variant="secondary")

    def _create_sample_preview_section(self):
        """Create sample menu preview section."""
        with gr.Accordion("📋 Sample Multi-Mode Menu", open=False):
            sample_content = """
### Example of Generated Smart Menu:

```
Ubuntu Multi-Mode PXE Boot
════════════════════════════════════════════════
Ubuntu Installation Options
── Ubuntu 24.04 LTS ──
🌐 Ubuntu 24.04 - Network Install
💿 Ubuntu 24.04 - Live Boot         (if ISO available)
⚡ Ubuntu 24.04 - Auto Install      (if preseed available)
🔧 Ubuntu 24.04 - Rescue Mode

── Ubuntu 22.04 LTS ──  
🌐 Ubuntu 22.04 - Network Install
🔧 Ubuntu 22.04 - Rescue Mode

System Tools
🛠️ Memory Test (Memtest86+)

🖥️  Drop to iPXE shell
🔄 Reboot computer
❌ Exit to BIOS
```

**Boot Mode Indicators:**
- 🌐 Network Install: Downloads from Ubuntu repositories (requires internet)
- 💿 Live Boot: Boots from local ISO file (requires ISO)
- ⚡ Auto Install: Uses preseed configuration (requires preseed.cfg)
- 🔧 Rescue Mode: Recovery and repair tools (always available)
            """
            gr.Markdown(sample_content)

    def _setup_event_handlers(self):
        """Setup all event handlers for the tab."""
        # Smart menu buttons
        self.create_smart_btn.click(
            fn=self._create_smart_ubuntu_menu,
            inputs=[self.menu_type, self.ipxe_server_ip, self.ipxe_port],
            outputs=[self.ipxe_status, self.ipxe_script_output]
        )

        self.analyze_btn.click(
            fn=self._get_ubuntu_capabilities_status,
            outputs=self.ubuntu_analysis
        )

        self.suggest_iso_btn.click(
            fn=self._create_ubuntu_iso_download_suggestions,
            outputs=self.ubuntu_analysis
        )

        # Menu validation and saving
        self.validate_btn.click(
            fn=self._validate_ipxe_script,
            inputs=[self.ipxe_script_output],
            outputs=self.ipxe_status
        )

        self.save_ipxe_btn.click(
            fn=self._save_ipxe_menu,
            inputs=[self.ipxe_script_output],
            outputs=self.ipxe_status
        )

        # Classic template
        self.create_template_btn.click(
            fn=self._create_ipxe_menu_from_template,
            inputs=[self.template_choice, self.ipxe_server_ip, self.ipxe_port],
            outputs=[self.ipxe_status, self.ipxe_script_output]
        )

        # Custom entry
        self.add_entry_btn.click(
            fn=self._add_custom_ipxe_entry,
            inputs=[
                self.ipxe_script_output, self.entry_name, self.entry_title,
                self.entry_kernel, self.entry_initrd, self.entry_cmdline,
                self.entry_description
            ],
            outputs=self.ipxe_script_output
        )

    # =========================
    # TAB-SPECIFIC METHODS
    # =========================

    @safe_method(module_attr='ipxe_manager', error_prefix='Smart Ubuntu menu creation')
    def _create_smart_ubuntu_menu(self, template_type: str = "multi",
                                  server_ip: str = "localhost",
                                  port: int = 8000) -> tuple:
        """Create smart Ubuntu menu with multiple boot options."""
        if not self.ui_controller.ipxe_manager:
            error_msg = "❌ iPXE manager module not available"
            return error_msg, ""

        try:
            # Create adaptive menu based on available files
            menu = self.ui_controller.ipxe_manager.create_adaptive_ubuntu_menu(
                server_ip.strip(), int(port), template_type
            )

            # Generate script
            is_valid, message, script_content = self.ui_controller.ipxe_manager.validate_and_generate(menu)

            if not is_valid:
                return message, ""

            # Get status info
            version_status = self.ui_controller.ipxe_manager.get_version_status()

            status_msg = f"✅ Smart Ubuntu menu created!\n"
            status_msg += f"📊 Found {version_status['versions_found']} Ubuntu versions\n\n"

            for version, info in version_status['versions'].items():
                status_msg += f"🐧 **Ubuntu {version}**:\n"
                status_msg += f"   • Boot options: {', '.join(info['boot_options'])}\n"
                status_msg += f"   • Recommended: {info['recommended']}\n"

                caps = info['capabilities']
                if caps['iso']:
                    status_msg += f"   • ✅ Live boot available (ISO found)\n"
                else:
                    status_msg += f"   • ❌ Live boot unavailable (ISO missing)\n"

                if caps['preseed']:
                    status_msg += f"   • ✅ Auto-install available (preseed found)\n"
                else:
                    status_msg += f"   • ❌ Auto-install unavailable (preseed missing)\n"
                status_msg += "\n"

            return status_msg, script_content

        except Exception as e:
            return f"❌ Smart menu creation failed: {str(e)}", ""

    @safe_method(module_attr='ipxe_manager', error_prefix='Ubuntu capabilities analysis')
    def _get_ubuntu_capabilities_status(self) -> str:
        """Get detailed Ubuntu capabilities status."""
        if not self.ui_controller.ipxe_manager:
            return "❌ iPXE manager module not available"

        try:
            versions = self.ui_controller.ipxe_manager.detector.scan_available_versions()

            if not versions:
                return "❌ No Ubuntu versions found in /srv/http/"

            status = "🐧 **Ubuntu Versions Analysis**\n"
            status += "=" * 50 + "\n\n"

            for version, capabilities in versions.items():
                status += f"📦 **Ubuntu {version} LTS**\n"
                status += f"   📁 Path: /srv/http/ubuntu-{version}/\n"

                # File status
                file_status = []
                if capabilities['kernel']:
                    file_status.append("✅ Kernel")
                else:
                    file_status.append("❌ Kernel")

                if capabilities['initrd']:
                    file_status.append("✅ Initrd")
                else:
                    file_status.append("❌ Initrd")

                if capabilities['iso']:
                    file_status.append("✅ ISO")
                else:
                    file_status.append("❌ ISO")

                if capabilities['preseed']:
                    file_status.append("✅ Preseed")
                else:
                    file_status.append("❌ Preseed")

                status += f"   📋 Files: {' | '.join(file_status)}\n"

                # Boot options
                boot_options = self.ui_controller.ipxe_manager.detector.get_boot_options_for_version(
                    version, capabilities
                )

                status += f"   🚀 **Available Boot Modes:**\n"
                for option in boot_options:
                    mode_info = {
                        "netboot": "🌐 Network Install (requires internet)",
                        "live": "💿 Live Boot (requires ISO)",
                        "rescue": "🔧 Rescue Mode",
                        "preseed": "⚡ Auto Install (requires preseed)"
                    }
                    status += f"      • {mode_info.get(option, option)}\n"

                if not boot_options:
                    status += f"      ❌ No boot options available (missing kernel/initrd)\n"

                status += "\n"

            # Summary recommendations
            status += "💡 **Recommendations:**\n"

            working_versions = [v for v, c in versions.items() if c['kernel'] and c['initrd']]
            if working_versions:
                status += f"✅ Working versions: {', '.join(working_versions)}\n"

            iso_missing = [v for v, c in versions.items() if c['kernel'] and c['initrd'] and not c['iso']]
            if iso_missing:
                status += f"💿 To enable Live Boot, download ISO files for: {', '.join(iso_missing)}\n"

            preseed_missing = [v for v, c in versions.items() if c['kernel'] and c['initrd'] and not c['preseed']]
            if preseed_missing:
                status += f"⚡ To enable Auto Install, add preseed.cfg for: {', '.join(preseed_missing)}\n"

            return status

        except Exception as e:
            return f"❌ Ubuntu analysis failed: {str(e)}"

    @safe_method(module_attr='ipxe_manager', error_prefix='ISO download suggestions')
    def _create_ubuntu_iso_download_suggestions(self) -> str:
        """Generate suggestions for downloading missing ISO files."""
        if not self.ui_controller.ipxe_manager:
            return "❌ iPXE manager module not available"

        try:
            versions = self.ui_controller.ipxe_manager.detector.scan_available_versions()

            suggestions = "💿 **Ubuntu ISO Download Suggestions**\n"
            suggestions += "=" * 50 + "\n\n"

            iso_needed = []
            for version, capabilities in versions.items():
                if capabilities['kernel'] and capabilities['initrd'] and not capabilities['iso']:
                    iso_needed.append(version)

            if not iso_needed:
                suggestions += "✅ All available Ubuntu versions have ISO files!\n"
                return suggestions

            suggestions += "📥 **Missing ISO files for:**\n\n"

            for version in iso_needed:
                suggestions += f"🐧 **Ubuntu {version} LTS**\n"

                # ISO download URLs
                if version == "24.04":
                    iso_url = "https://releases.ubuntu.com/noble/ubuntu-24.04.2-live-server-amd64.iso"
                elif version == "22.04":
                    iso_url = "https://releases.ubuntu.com/jammy/ubuntu-22.04.5-live-server-amd64.iso"
                elif version == "20.04":
                    iso_url = "https://releases.ubuntu.com/focal/ubuntu-20.04.6-live-server-amd64.iso"
                else:
                    iso_url = f"https://releases.ubuntu.com/ubuntu-{version}-live-server-amd64.iso"

                target_path = f"/srv/http/ubuntu-{version}/ubuntu-{version}-live-server-amd64.iso"

                suggestions += f"   📎 URL: {iso_url}\n"
                suggestions += f"   📁 Target: {target_path}\n"
                suggestions += f"   📦 Size: ~2.5GB\n"
                suggestions += f"   ⚡ Command: `wget {iso_url} -O {target_path}`\n\n"

            suggestions += "💡 **Benefits of having ISO files:**\n"
            suggestions += "   • 💿 Enable Live Boot mode (test without installing)\n"
            suggestions += "   • 🚀 Faster installation (no internet download)\n"
            suggestions += "   • 🔒 Offline installation capability\n"
            suggestions += "   • 🎯 Complete Ubuntu experience\n"

            return suggestions

        except Exception as e:
            return f"❌ ISO suggestions failed: {str(e)}"

    @safe_method(module_attr='ipxe_manager', error_prefix='iPXE template creation')
    def _create_ipxe_menu_from_template(self, template_name: str,
                                        server_ip: str = "localhost",
                                        port: int = 8000) -> tuple:
        """Create iPXE menu from template with auto-detection of Ubuntu versions."""
        if not self.ui_controller.ipxe_manager:
            error_msg = "❌ iPXE manager module not available"
            return error_msg, ""

        try:
            menu = self.ui_controller.ipxe_manager.get_template(
                template_name, server_ip.strip(), int(port)
            )

            if not menu:
                return f"❌ Template '{template_name}' not found", ""

            # If template is Ubuntu-related, add all installed versions
            if template_name == "ubuntu" and self.ui_controller.ubuntu_downloader:
                installed_versions = self.ui_controller.ubuntu_downloader.get_installed_versions()
                if installed_versions:
                    # Import iPXEEntry for creating entries
                    from ..backend.ipxe_manager import iPXEEntry

                    # Clear existing Ubuntu entries and add all installed versions
                    menu.entries = [e for e in menu.entries if "ubuntu" not in e.name.lower()]

                    for i, version in enumerate(installed_versions):
                        entry = iPXEEntry(
                            name=f"ubuntu_{version.replace('.', '_')}",
                            title=f"Ubuntu {version} LTS",
                            kernel=f"ubuntu-{version}/vmlinuz",
                            initrd=f"ubuntu-{version}/initrd",
                            cmdline=f"ip=dhcp url=http://{server_ip}:{port}/http/ubuntu-{version}/preseed.cfg",
                            description=f"Ubuntu {version} automated installation",
                            order=i + 1
                        )
                        menu.entries.append(entry)

                    menu.default_entry = f"ubuntu_{installed_versions[0].replace('.', '_')}"

            is_valid, message, script_content = self.ui_controller.ipxe_manager.validate_and_generate(menu)
            return message, script_content if is_valid else ""

        except Exception as e:
            return f"❌ Template creation failed: {str(e)}", ""

    def _validate_ipxe_script(self, script_content: str) -> str:
        """Validate iPXE script."""
        if not script_content or not script_content.strip():
            return "❌ No script content to validate"

        # Basic validation
        script = script_content.strip()

        if not script.startswith("#!ipxe"):
            return "⚠️ Script should start with '#!ipxe'"

        if ":start" not in script:
            return "⚠️ Script should contain ':start' label"

        if "choose" not in script:
            return "⚠️ Script should contain 'choose' command"

        # Count menu items
        item_count = script.count("item ")
        if item_count == 0:
            return "⚠️ Script should contain at least one menu item"

        return f"✅ iPXE script validation passed ({item_count} menu items found)"

    def _save_ipxe_menu(self, script_content: str) -> str:
        """Save iPXE menu script."""
        if not script_content or not script_content.strip():
            return "❌ No script content to save"

        try:
            import os

            # Determine file path based on OS
            if os.name == 'nt':  # Windows
                filepath = "C:/srv/ipxe/boot.ipxe"
            else:  # Unix-like
                filepath = "/srv/ipxe/boot.ipxe"

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # Save to file
            with open(filepath, "w") as f:
                f.write(script_content)

            return f"✅ iPXE menu saved to {filepath}"

        except Exception as e:
            return f"❌ Save failed: {str(e)}"

    def _add_custom_ipxe_entry(self, menu_script: str, entry_name: str, entry_title: str,
                               kernel_path: str, initrd_path: str = "", cmdline: str = "",
                               description: str = "") -> str:
        """Add custom entry to iPXE menu."""
        if not menu_script or not menu_script.strip():
            return "❌ No menu script provided"

        if not entry_name or not entry_title or not kernel_path:
            return "❌ Entry name, title, and kernel path are required"

        try:
            # Sanitize entry name
            import re
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', entry_name.strip())

            # Create new entry section
            new_entry_section = f"""
:{safe_name}
echo Booting {entry_title.strip()}...
"""
            if description.strip():
                new_entry_section += f"echo {description.strip()}\n"

            new_entry_section += f"kernel {kernel_path.strip()} {cmdline.strip()}\n"

            if initrd_path.strip():
                new_entry_section += f"initrd {initrd_path.strip()}\n"

            new_entry_section += """boot
goto start

"""

            # Add menu item (simplified)
            menu_item = f"item {safe_name} {entry_title.strip()}\n"

            # Insert into script (basic implementation)
            if "item --gap --" in menu_script:
                updated_script = menu_script.replace(
                    "item --gap --\nitem shell",
                    f"item --gap --\n{menu_item}item shell"
                )
                updated_script += new_entry_section
                return updated_script
            else:
                return menu_script + "\n" + menu_item + new_entry_section

        except Exception as e:
            return f"❌ Failed to add custom entry: {str(e)}"

    # =========================
    # TAB VALIDATION
    # =========================

    def validate_tab(self) -> Optional[str]:
        """
        Validate that this tab can function properly.

        Returns:
            Error message if validation fails, None if successful
        """
        return self._validate_required_modules(['ipxe_manager'])

    def get_debug_info(self) -> str:
        """Get debug information for this tab."""
        info = [
            f"Tab: {self.tab_name}",
            f"Components: {len(self._components)}",
            f"iPXE Manager Available: {bool(self.ui_controller.ipxe_manager)}",
            f"Ubuntu Downloader Available: {bool(self.ui_controller.ubuntu_downloader)}",
        ]

        validation_error = self.validate_tab()
        if validation_error:
            info.append(f"Validation Error: {validation_error}")
        else:
            info.append("Validation: ✅ Passed")

        return "\n".join(info)
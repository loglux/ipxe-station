from app.ui_tabs.base_tab import PXEBootStationUI
from app.ui_tabs.helpers import _create_action_buttons, _create_status_textbox
from app.backend.ipxe_menu.entry_model import iPXEEntry
from app.backend.ipxe_menu.menu_manager import MenuManager
from app.backend.boot_templates import BOOT_TEMPLATES
import uuid
import gradio as gr


class iPXETab:
    def __init__(self, ui_controller: PXEBootStationUI):
        self.ui_controller = ui_controller
        # call MenuManager from menu_state
        self.menu = MenuManager()
        self.entry_options = []  # list (label, id)


    def add_entry(self, label, command, parent_id):
        entry_id = str(uuid.uuid4())[:8]
        entry = iPXEEntry(
            id=entry_id,
            label=label,
            command=command,
        )
        self.menu.add_entry(entry, parent_id=parent_id or None)
        self.entry_options.append((label, entry_id))  # update the list.

        return self.format_tree(), gr.update(choices=self.entry_options)

    def format_tree(self):
        def walk(entry: iPXEEntry, indent: int = 0):
            prefix = "    " * indent
            lines = [f"{prefix}- {entry.label} ({entry.id})"]
            for child in entry.children:
                lines.extend(walk(child, indent + 1))
            return lines

        result = []
        for e in self.menu.root_entries:
            result.extend(walk(e))
        return "\n".join(result)

    def generate_script(self):
        return self.menu.generate_script()

    def delete_entry_fn(self, entry_id: str):
        success = self.menu.delete_entry(entry_id.strip())
        return self.format_tree()

    def clear_menu(self):
        self.menu = MenuManager()
        return self.format_tree()

    def move_entry_up(self, entry_id: str):
        self.menu.move_entry(entry_id.strip(), "up")
        return self.format_tree()

    def move_entry_down(self, entry_id: str):
        self.menu.move_entry(entry_id.strip(), "down")
        return self.format_tree()

    def fill_fields_from_template(self, template_name: str):
        tpl = BOOT_TEMPLATES.get(template_name, {})
        return (
            tpl.get("kernel", ""),
            tpl.get("initrd", ""),
            tpl.get("cmdline", ""),
            tpl.get("imgargs", "")
        )

    def create_tab(self):
        with gr.Tab("📋 iPXE Menu"):
            gr.Markdown("## 📋 Enhanced iPXE Boot Menu Configuration")
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Smart Menu Generation")

                    menu_type = gr.Dropdown(
                        choices=[
                            ("Multi-Mode Menu (All Options)", "multi"),
                            ("Quick Menu (Netboot Only)", "quick")
                        ],
                        value="multi",
                        label="Menu Type"
                    )

                    ipxe_server_ip = gr.Textbox(
                        value="192.168.1.10",
                        label="PXE Server IP"
                    )
                    ipxe_port = gr.Number(
                        value=8000,
                        label="HTTP Port",
                        precision=0
                    )

                    with gr.Row():
                        create_smart_btn, analyze_btn, suggest_iso_btn = _create_action_buttons(
                            ("Create Smart Menu", "primary", "🎨"),
                            ("Analyze Ubuntu Files", "secondary", "🔍"),
                            ("ISO Suggestions", "secondary", "💿")
                        )

            with gr.Row():
                with gr.Column():
                    ipxe_status = _create_status_textbox(
                        label="Menu Status",
                        lines=8
                    )

                with gr.Column():
                    ubuntu_analysis = _create_status_textbox(
                        label="Ubuntu Analysis",
                        lines=8
                    )

            ipxe_script_output = gr.Code(
                label="Generated iPXE Boot Script",
                language="shell",
                lines=25,
                interactive=True
            )

            with gr.Row():
                validate_btn, save_ipxe_btn = _create_action_buttons(
                    ("Validate Script", "secondary", "✅"),
                    ("Save Menu", "primary", "💾")
                )

            create_smart_btn.click(
                fn=self.ui_controller.create_smart_ubuntu_menu,
                inputs=[menu_type, ipxe_server_ip, ipxe_port],
                outputs=[ipxe_status, ipxe_script_output]
            )

            analyze_btn.click(
                fn=self.ui_controller.get_ubuntu_capabilities_status,
                outputs=ubuntu_analysis
            )

            suggest_iso_btn.click(
                fn=self.ui_controller.create_ubuntu_iso_download_suggestions,
                outputs=ubuntu_analysis
            )

            validate_btn.click(
                fn=self.ui_controller.validate_ipxe_script,
                inputs=[ipxe_script_output],
                outputs=ipxe_status
            )

            save_ipxe_btn.click(
                fn=self.ui_controller.save_ipxe_menu,
                inputs=[ipxe_script_output],
                outputs=ipxe_status
            )

            with gr.Accordion("➕ Add Custom Entry", open=False):
                gr.Markdown("### Add Custom Boot Entry")

                with gr.Row():
                    with gr.Column():
                        template_select = gr.Dropdown(
                            label="Boot Template",
                            choices=list(BOOT_TEMPLATES.keys()),
                            value=None,
                            interactive=True
                        )
                        entry_name = gr.Textbox(label="Entry Name (ID)", placeholder="my_custom_os")
                        entry_title = gr.Textbox(label="Display Title", placeholder="My Custom OS")
                        entry_description = gr.Textbox(label="Description (optional)")

                    with gr.Column():
                        entry_kernel = gr.Textbox(label="Kernel Path", placeholder="custom/vmlinuz")
                        entry_initrd = gr.Textbox(label="Initrd Path (optional)", placeholder="custom/initrd")
                        entry_cmdline = gr.Textbox(label="Kernel Command Line", placeholder="ip=dhcp root=/dev/nfs")
                        entry_imgargs = gr.Textbox(label="imgargs (optional)", placeholder="root=live:CDLABEL=...")

                add_entry_btn = gr.Button("➕ Add Entry to Menu")

                # Auto-fill from template
                template_select.change(
                    fn=self.fill_fields_from_template,
                    inputs=[template_select],
                    outputs=[entry_kernel, entry_initrd, entry_cmdline, entry_imgargs]
                )

                add_entry_btn.click(
                    fn=self.ui_controller.add_custom_ipxe_entry,
                    inputs=[
                        # ipxe_script_output,
                        entry_name, entry_title,
                        entry_kernel, entry_initrd,
                        entry_cmdline, entry_imgargs,
                        entry_description
                    ],
                    outputs=ipxe_script_output
                )

            # backend/menu_state.py
            with gr.Accordion("🧪 Menu Tree Editor (Experimental)", open=False):
                with gr.Row():
                    new_label = gr.Textbox(label="Label")
                    new_command = gr.Textbox(label="Command (optional)")
                    # new_parent_id = gr.Textbox(label="Parent ID (optional)")
                    new_parent_id = gr.Dropdown(label="Parent Entry (optional)", choices=[], interactive=True)

                add_tree_btn = gr.Button("➕ Add Entry to Tree")

                tree_output = gr.Textbox(label="Current Menu Tree", lines=12)
                script_output = gr.Code(label="Generated iPXE Script", language="shell", lines=20)

                add_tree_btn.click(
                    fn=self.add_entry,
                    inputs=[new_label, new_command, new_parent_id],
                    outputs=[tree_output, new_parent_id]
                )

                gr.Markdown("### Delete Entry by ID")
                delete_id_input = gr.Textbox(label="Entry ID to Delete")
                delete_btn = gr.Button("❌ Delete Entry")

                delete_btn.click(
                    fn=self.delete_entry_fn,
                    inputs=[delete_id_input],
                    outputs=tree_output
                )

                gr.Markdown("### Move Entry")
                move_id_input = gr.Textbox(label="Entry ID to Move")
                with gr.Row():
                    move_up_btn = gr.Button("⬆️ Move Up")
                    move_down_btn = gr.Button("⬇️ Move Down")

                clear_btn = gr.Button("🧹 Clear All Entries")
                clear_btn.click(
                    fn=self.clear_menu,
                    outputs=tree_output
                )

                move_up_btn.click(
                    fn=self.move_entry_up,
                    inputs=[move_id_input],
                    outputs=tree_output
                )

                move_down_btn.click(
                    fn=self.move_entry_down,
                    inputs=[move_id_input],
                    outputs=tree_output
                )

                gen_script_btn = gr.Button("🚀 Generate iPXE Script")
                gen_script_btn.click(fn=self.generate_script, outputs=script_output)

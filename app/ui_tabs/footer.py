# app/ui_tabs/footer.py
import gradio as gr

class Footer:
    def __init__(self, ui_controller):
        self.ui_controller = ui_controller

    def create_tab(self):
        """Создает footer для UI"""
        gr.HTML("""
        <div style="text-align: center; padding: 20px; margin-top: 30px; border-top: 1px solid #ddd;">
            <p>🚀 <strong>PXE Boot Station</strong> - Network Boot Management Made Easy</p>
            <p style="color: #666;">DHCP • TFTP • iPXE • ISO Management • Ubuntu Automation</p>
        </div>
        """)


# class Footer:
#     def __init__(self, ui_controller):
#         self.ui_controller = ui_controller
#
#     def create_tab(self):
#         """Создает footer для UI"""
#         with gr.Row():
#             gr.Markdown(
#                 """
#                 ---
#                 <div style='text-align: center; color: #666; font-size: 12px; padding: 10px;'>
#                     <p>🚀 <strong>PXE Boot Station</strong> |
#                     Network Boot Management System |
#                     <em>Powered by Gradio</em></p>
#                 </div>
#                 """,
#                 elem_id="footer"
#             )
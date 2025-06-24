import gradio as gr


class Header:
    def __init__(self, ui_controller):
        self.ui_controller = ui_controller

    def create_tab(self):
        """Создает header для UI"""
        gr.HTML("""
        <div style="text-align: center; padding: 20px; background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 10px; margin-bottom: 20px;">
            <h1>🚀 PXE Boot Station Control Panel</h1>
            <p>Complete PXE network boot management solution</p>
        </div>
        """)
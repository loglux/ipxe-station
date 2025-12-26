import gradio as gr
from app.ui_tabs.base_tab import PXEBootStationUI
from app.ui_tabs import TAB_REGISTRY, Header, Footer

custom_css = """
.gradio-container {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
.tab-nav {
    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
}
.status-good { color: #28a745; }
.status-warning { color: #ffc107; }
.status-error { color: #dc3545; }
"""


def build_gradio_ui():
    ui_controller = PXEBootStationUI()
    with gr.Blocks(
            title="PXE Boot Station",
            theme=gr.themes.Soft(),
            css=custom_css
                    ) as demo:
        # Header
        Header(ui_controller).create_tab()
       # Tabs
        with gr.Tabs():
            for tab_class in TAB_REGISTRY:
                tab_class(ui_controller).create_tab()
        # Footer
        Footer(ui_controller).create_tab()

    return demo

demo = build_gradio_ui()

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=9005,
        share=False,
        show_error=True,
        debug=False
    )

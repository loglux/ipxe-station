# fastapi_main.py

from fastapi import FastAPI
from fastapi.responses import RedirectResponse, FileResponse
import gradio as gr

from gradio_ui import build_gradio_ui  # Убрали app.

# Build the Gradio UI
demo = build_gradio_ui()

# FastAPI setup, OpenAPI under /api
app = FastAPI(
    title="iPXE Station",
    version="0.2.0",
)

@app.get("/", include_in_schema=False)
def root():
    # Redirect root URL to the Gradio interface
    return RedirectResponse("/pxe-station")

# Mount Gradio UI at /gradio
app = gr.mount_gradio_app(app, demo, path="/pxe-station")

@app.get("/api/ping")
def ping():
    return {"status": "ok"}

@app.api_route("/ipxe/boot.ipxe", methods=["GET", "HEAD"])
def get_ipxe_script():
    return FileResponse("ipxe/boot.ipxe", media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    print("🚀 iPXE Station (FastAPI + Gradio)")
    print("🌐 UI: http://localhost:8000/pxe-station")
    print("📄 API docs: http://localhost:8000/api/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
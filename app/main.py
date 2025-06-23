from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, RedirectResponse
import gradio as gr
from gradio_ui import build_gradio_ui
import os
from pathlib import Path

app = FastAPI(title="iPXE Station", description="Network Boot Server")

# Mount static file serving for HTTP boot
app.mount("/http", StaticFiles(directory="/srv/http"), name="http")

# Mount iPXE files
@app.get("/ipxe/{filename}")
async def serve_ipxe(filename: str):
    """Serve iPXE files"""
    file_path = Path(f"/srv/ipxe/{filename}")
    if file_path.exists():
        return FileResponse(file_path)
    return Response("File not found", status_code=404)

# Mount TFTP files (for HTTP access if needed)
@app.get("/tftp/{filename}")
async def serve_tftp(filename: str):
    """Serve TFTP files via HTTP"""
    file_path = Path(f"/srv/tftp/{filename}")
    if file_path.exists():
        return FileResponse(file_path)
    return Response("File not found", status_code=404)

@app.get("/")
async def root():
    """Redirect to Gradio UI"""
    return RedirectResponse(url="/pxe-station")

@app.get("/status")
async def status():
    """Server status"""
    return {
        "tftp_files": len(list(Path("/srv/tftp").glob("*"))),
        "http_files": len(list(Path("/srv/http").rglob("*"))),
        "ipxe_files": len(list(Path("/srv/ipxe").glob("*")))
    }

@app.get("/ipxe/boot.ipxe")
def get_ipxe_script():
    return FileResponse("ipxe/boot.ipxe", media_type="text/plain")

# Create and mount Gradio interface
print("Creating Gradio UI...")
gradio_app = build_gradio_ui()

# Mount Gradio at /pxe-station
print("Mounting Gradio app...")
app = gr.mount_gradio_app(app, gradio_app, path="/pxe-station")

if __name__ == "__main__":
    import uvicorn
    print("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
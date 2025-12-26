from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, RedirectResponse
import gradio as gr
from app.gradio_ui import build_gradio_ui
import os
from pathlib import Path
from fastapi import APIRouter

from app.backend.ipxe_manager import iPXEManager
from app.backend.ipxe_schema import IpxeMenuModel, model_to_menu

app = FastAPI(title="iPXE Station", description="Network Boot Server")

# Base data root (fallback to /tmp/ipxe if /srv not writable)
BASE_ROOT = Path(os.getenv("IPXE_DATA_ROOT", "/srv"))
try:
    BASE_ROOT.mkdir(parents=True, exist_ok=True)
except PermissionError:
    BASE_ROOT = Path("/tmp/ipxe")
    BASE_ROOT.mkdir(parents=True, exist_ok=True)

HTTP_ROOT = BASE_ROOT / "http"
IPXE_ROOT = BASE_ROOT / "ipxe"
TFTP_ROOT = BASE_ROOT / "tftp"

for d in (HTTP_ROOT, IPXE_ROOT, TFTP_ROOT):
    d.mkdir(parents=True, exist_ok=True)

# Mount static file serving for HTTP boot
app.mount("/http", StaticFiles(directory=str(HTTP_ROOT)), name="http")

# Mount iPXE files
@app.get("/ipxe/{filename}")
@app.head("/ipxe/{filename}")
async def serve_ipxe(filename: str):
    """Serve iPXE files"""
    file_path = IPXE_ROOT / filename
    if file_path.exists():
        return FileResponse(
            file_path,
        media_type="text/plain",
        headers={"Cache-Control": "no-cache"})
    return Response("File not found", status_code=404)

# Mount TFTP files (for HTTP access if needed)
@app.get("/tftp/{filename}")
async def serve_tftp(filename: str):
    """Serve TFTP files via HTTP"""
    file_path = TFTP_ROOT / filename
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
        "tftp_files": len(list(TFTP_ROOT.glob("*"))),
        "http_files": len(list(HTTP_ROOT.rglob("*"))),
        "ipxe_files": len(list(IPXE_ROOT.glob("*")))
    }


# API: iPXE config validation/generation
ipxe_router = APIRouter(prefix="/api/ipxe", tags=["ipxe"])
ipxe_manager = iPXEManager(config_path=IPXE_ROOT / "boot.ipxe")


@ipxe_router.post("/validate")
def validate_ipxe(menu: IpxeMenuModel):
    menu_dc = model_to_menu(menu)
    is_valid, errors = ipxe_manager.validator.validate_menu(menu_dc)
    warnings = ipxe_manager.validator.lint_menu(menu_dc)
    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
    }


@ipxe_router.post("/generate")
def generate_ipxe(menu: IpxeMenuModel):
    menu_dc = model_to_menu(menu)
    is_valid, message, script_content = ipxe_manager.validate_and_generate(menu_dc)
    warnings = ipxe_manager.validator.lint_menu(menu_dc)
    return {
        "valid": is_valid,
        "message": message,
        "warnings": warnings,
        "script": script_content if is_valid else "",
    }


@ipxe_router.get("/templates")
def list_templates():
    return {"templates": ["ubuntu", "ubuntu_multi", "ubuntu_quick", "diagnostic", "multi_os"]}


@ipxe_router.post("/templates/{template_name}")
def get_template(template_name: str, server_ip: str = "localhost", port: int = 8000):
    menu = ipxe_manager.get_template(template_name, server_ip=server_ip, port=port)
    if not menu:
        return Response("Template not found", status_code=404)
    model = menu_to_model(menu)
    return model.model_dump()


@ipxe_router.post("/menu/save")
def save_menu(menu: IpxeMenuModel):
    menu_dc = model_to_menu(menu)
    is_valid, message, script_content = ipxe_manager.validate_and_generate(menu_dc)
    warnings = ipxe_manager.validator.lint_menu(menu_dc)
    if not is_valid:
        return {
            "valid": False,
            "message": message,
            "warnings": warnings,
            "script": "",
        }
    ok, save_msg = ipxe_manager.save_menu(menu_dc)
    return {
        "valid": ok,
        "message": save_msg if ok else message,
        "warnings": warnings,
        "script": script_content if ok else "",
        "config_path": str(ipxe_manager.config_path),
    }


app.include_router(ipxe_router)

# Serve built frontend (Vite) if present
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/ui", StaticFiles(directory=FRONTEND_DIST, html=True), name="ui")

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

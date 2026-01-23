from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from cli_api.api.router import api_router

def create_app() -> FastAPI:
    app = FastAPI(
        title="Greymatter Bootstrap",
        version="0.1.0",
        description="Orchestrates Greymatter bootstrap workflows via Kubernetes Jobs.",
        docs_url="/api/swagger",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # API lives under /api
    app.include_router(api_router, prefix="/api")

    # Static UI
    web_dir = Path(__file__).parent / "web"
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(web_dir / "index.html"))

    @app.get("/health")
    def health():
        return {"ok": True}

    return app

app = create_app()

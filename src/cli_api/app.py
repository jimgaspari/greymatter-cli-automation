from fastapi import FastAPI
from cli_api.routes import git, kubectl, greymatter

def create_app() -> FastAPI:
    app = FastAPI(title="CLI Runner API", version="0.1.0")

    @app.get("/health")
    def health():
        return {"ok": True}

    app.include_router(git.router)
    app.include_router(kubectl.router)
    app.include_router(greymatter.router)
    return app

app = create_app()

def main():
    # Lets you run: cli-runner-api
    import uvicorn
    uvicorn.run("cli_runner_api.app:app", host="0.0.0.0", port=8080, reload=True)

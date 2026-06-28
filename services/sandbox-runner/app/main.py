from fastapi import FastAPI

from dieaudit_common.settings import get_settings

from app.application.sandbox import SandboxService
from app.runtime.docker_sandbox import DockerSandbox

settings = get_settings()
app = FastAPI(title="DieAudit Sandbox Runner", version="0.2.0")


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": settings.service_name}


@app.get("/ready")
async def ready() -> dict:
    return {"ok": True, "service": settings.service_name}


@app.get("/internal/sandbox/capabilities")
async def capabilities() -> dict:
    return await DockerSandbox().capabilities()


@app.post("/internal/sandbox/poc")
async def run_poc(payload: dict) -> dict:
    return await SandboxService().run_poc(payload)

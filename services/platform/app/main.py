from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.api.routes import register_runtime_routes
from app.repositories import init_db
from app.runtime import RuntimeOrchestrator
from app.settings import get_settings


settings = get_settings()
runtime: RuntimeOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runtime
    if settings.service_name == "web-api":
        await init_db()
    if settings.service_name in {"agent-gateway", "sandbox-runner"}:
        runtime = RuntimeOrchestrator(settings)
    yield
    if runtime:
        await runtime.close()


app = FastAPI(title=f"DieAudit {settings.service_name}", version="0.1.0", lifespan=lifespan)


def get_runtime() -> RuntimeOrchestrator | None:
    return runtime


app.include_router(register_runtime_routes(settings, get_runtime))

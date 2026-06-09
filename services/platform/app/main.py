from contextlib import asynccontextmanager
import secrets
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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


PUBLIC_PATHS = {"/", "/health", "/ready", "/auth/status"}


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    if _is_public_path(request.url.path) or not settings.dieaudit_api_key:
        return await call_next(request)
    supplied = request.headers.get(settings.api_key_header) or _bearer_token(request.headers.get("Authorization"))
    if supplied and secrets.compare_digest(supplied, settings.dieaudit_api_key):
        return await call_next(request)
    return JSONResponse({"detail": "missing or invalid API key"}, status_code=401)


def get_runtime() -> RuntimeOrchestrator | None:
    return runtime


app.include_router(register_runtime_routes(settings, get_runtime))


def _is_public_path(path: str) -> bool:
    if path == "/metrics" and settings.public_metrics:
        return True
    return path in PUBLIC_PATHS


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    prefix = "Bearer "
    if value.startswith(prefix):
        return value[len(prefix) :]
    return None


@app.get("/auth/status")
async def auth_status() -> dict[str, Any]:
    return {
        "enabled": bool(settings.dieaudit_api_key),
        "api_key_header": settings.api_key_header,
        "public_metrics": settings.public_metrics,
        "service": settings.service_name,
    }

from contextlib import asynccontextmanager
import time
import secrets
from typing import Any
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import register_runtime_routes
from app.domain.models import PlatformAuditEvent
from app.repositories import SessionLocal, init_db
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
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    path = request.url.path
    public_path = _is_public_path(path)
    auth_enabled = bool(settings.dieaudit_api_key)
    auth_result = "not_required"
    started = time.perf_counter()
    if public_path or not auth_enabled:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-Id"] = request_id
        await _record_platform_audit_event(request, status_code, request_id, auth_enabled, auth_result, started)
        return response
    supplied = request.headers.get(settings.api_key_header) or _bearer_token(request.headers.get("Authorization"))
    if supplied and secrets.compare_digest(supplied, settings.dieaudit_api_key):
        auth_result = "success"
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-Id"] = request_id
        await _record_platform_audit_event(request, status_code, request_id, auth_enabled, auth_result, started)
        return response
    auth_result = "failed"
    response = JSONResponse({"detail": "missing or invalid API key"}, status_code=401)
    response.headers["X-Request-Id"] = request_id
    await _record_platform_audit_event(request, 401, request_id, auth_enabled, auth_result, started)
    return response


def get_runtime() -> RuntimeOrchestrator | None:
    return runtime


app.include_router(register_runtime_routes(settings, get_runtime))


def _is_public_path(path: str) -> bool:
    if path == "/metrics" and settings.public_metrics:
        return True
    return path in PUBLIC_PATHS


def _should_record_platform_event(path: str) -> bool:
    return path not in {"/", "/health", "/ready", "/auth/status", "/metrics"}


async def _record_platform_audit_event(
    request: Request,
    status_code: int,
    request_id: str,
    auth_enabled: bool,
    auth_result: str,
    started: float,
) -> None:
    path = request.url.path
    if not _should_record_platform_event(path):
        return
    try:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        client_host = request.client.host if request.client else None
        async with SessionLocal() as session:
            session.add(
                PlatformAuditEvent(
                    service=settings.service_name,
                    method=request.method,
                    path=path,
                    status_code=status_code,
                    client_host=client_host,
                    user_agent=request.headers.get("User-Agent"),
                    auth_enabled=auth_enabled,
                    auth_result=auth_result,
                    request_id=request_id,
                    metadata_json={
                        "query": str(request.url.query or ""),
                        "duration_ms": duration_ms,
                        "forwarded_for": request.headers.get("X-Forwarded-For"),
                    },
                )
            )
            await session.commit()
    except Exception:
        # Audit logging must never break the API path it is observing.
        return


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

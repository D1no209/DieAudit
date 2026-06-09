from contextlib import asynccontextmanager
import time
from typing import Any
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import register_runtime_routes
from app.domain.models import PlatformAuditEvent
from app.repositories import SessionLocal, init_db
from app.runtime import RuntimeOrchestrator
from app.services.auth import (
    auth_is_enabled,
    authenticate_api_key,
    can_access_scope,
    required_scope_for_path,
    reset_current_api_key,
    set_current_api_key,
)
from app.services.pipeline_recovery import recover_interrupted_pipelines
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
    if settings.service_name == "agent-gateway" and settings.pipeline_recovery_on_startup:
        await recover_interrupted_pipelines(service_name=settings.service_name)
    yield
    if runtime:
        await runtime.close()


app = FastAPI(title=f"DieAudit {settings.service_name}", version="0.1.0", lifespan=lifespan)


PUBLIC_PATHS = {"/", "/health", "/ready", "/auth/status"}


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    current_api_key_token = set_current_api_key(None)
    forwarded_api_key_token = None
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    path = request.url.path
    public_path = _is_public_path(path)
    auth_enabled = bool(settings.dieaudit_api_key) if public_path else await auth_is_enabled(settings)
    auth_result = "not_required"
    auth_principal: dict[str, Any] | None = None
    started = time.perf_counter()
    try:
        if public_path or not auth_enabled:
            request.state.auth_principal = auth_principal
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-Id"] = request_id
            await _record_platform_audit_event(request, status_code, request_id, auth_enabled, auth_result, auth_principal, started)
            return response
        supplied = request.headers.get(settings.api_key_header) or _bearer_token(request.headers.get("Authorization"))
        auth_principal = await authenticate_api_key(settings, supplied)
        if auth_principal:
            forwarded_api_key_token = set_current_api_key(supplied)
            auth_result = "success"
            request.state.auth_principal = auth_principal
            required_scope = required_scope_for_path(request.method, path)
            if not can_access_scope(auth_principal, required_scope, request.method):
                auth_result = "insufficient_scope"
                response = JSONResponse(
                    {
                        "detail": "insufficient API key scope",
                        "required_scope": required_scope,
                    },
                    status_code=403,
                )
                response.headers["X-Request-Id"] = request_id
                await _record_platform_audit_event(request, 403, request_id, auth_enabled, auth_result, auth_principal, started)
                return response
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-Id"] = request_id
            await _record_platform_audit_event(request, status_code, request_id, auth_enabled, auth_result, auth_principal, started)
            return response
        auth_result = "failed"
        request.state.auth_principal = None
        response = JSONResponse({"detail": "missing or invalid API key"}, status_code=401)
        response.headers["X-Request-Id"] = request_id
        await _record_platform_audit_event(request, 401, request_id, auth_enabled, auth_result, auth_principal, started)
        return response
    finally:
        if forwarded_api_key_token is not None:
            reset_current_api_key(forwarded_api_key_token)
        reset_current_api_key(current_api_key_token)


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
    auth_principal: dict[str, Any] | None,
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
                        "auth_key_id": (auth_principal or {}).get("key_id"),
                        "auth_source": (auth_principal or {}).get("source"),
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
    enabled = await auth_is_enabled(settings)
    return {
        "enabled": enabled,
        "bootstrap_key_enabled": bool(settings.dieaudit_api_key),
        "api_key_header": settings.api_key_header,
        "public_metrics": settings.public_metrics,
        "service": settings.service_name,
    }

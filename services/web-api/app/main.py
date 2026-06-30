from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.bff.routes import admin, agent_messages, agent_runtimes, audit_runs, findings, knowledge, projects, reports, runtime, session
from app.settings import get_settings


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="DieAudit Web BFF", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def error_envelope(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    try:
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
    except Exception as exc:
        return JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": str(exc),
                    "request_id": request_id,
                    "details": {},
                }
            },
            status_code=500,
            headers={"X-Request-Id": request_id},
        )


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": settings.service_name}


@app.get("/ready")
async def ready() -> dict:
    return {"ok": True, "service": settings.service_name, "bff_prefix": "/api/bff"}


app.include_router(session.router)
app.include_router(agent_runtimes.router)
app.include_router(agent_messages.router)
app.include_router(projects.router)
app.include_router(audit_runs.router)
app.include_router(findings.router)
app.include_router(reports.router)
app.include_router(runtime.router)
app.include_router(knowledge.router)
app.include_router(admin.router)

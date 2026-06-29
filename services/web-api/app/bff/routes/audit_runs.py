from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import select

from dieaudit_common.domain.models import AuditRun
from dieaudit_common.persistence.base import SessionLocal
from dieaudit_common.schemas.bff import CancelAuditRunPayload, CreateAuditRunPayload, StartAuditRunPayload
from dieaudit_common.settings import get_settings

from app.application.audit_runs import AuditRunApplication

router = APIRouter(prefix="/api/bff/audit-runs", tags=["audit-runs"])


async def _mark_worker_failure(audit_run_id: str, exc: Exception) -> None:
    async with SessionLocal() as session:
        row = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
        if row is None:
            return
        row.status = "failed"
        row.pipeline_status = "failed"
        row.current_stage = None
        row.metadata_json = {
            **(row.metadata_json or {}),
            "worker_error": str(exc),
        }
        await session.commit()


async def _run_pipeline_worker(audit_run_id: str) -> None:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(f"{settings.workflow_worker_url}/internal/pipelines/{audit_run_id}/run")
            response.raise_for_status()
    except Exception as exc:  # pragma: no cover - defensive background task guard
        await _mark_worker_failure(audit_run_id, exc)


@router.get("")
async def list_audit_runs() -> list[dict]:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).list_audit_runs()


@router.post("")
async def create_audit_run(payload: CreateAuditRunPayload) -> dict:
    async with SessionLocal() as session:
        result = await AuditRunApplication(session).create_audit_run(payload.model_dump())
        await session.commit()
        return result


@router.get("/{audit_run_id}")
async def get_audit_run(audit_run_id: str) -> dict:
    async with SessionLocal() as session:
        result = await AuditRunApplication(session).get_audit_run(audit_run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="audit run not found")
        return result


@router.post("/{audit_run_id}/start")
async def start_audit_run(audit_run_id: str, payload: StartAuditRunPayload, background_tasks: BackgroundTasks) -> dict[str, Any]:
    async with SessionLocal() as session:
        result = await AuditRunApplication(session).queue_audit_run(audit_run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="audit run not found")
        await session.commit()
    background_tasks.add_task(_run_pipeline_worker, audit_run_id)
    return {"queued": True, "force": payload.force, "audit_run": result}


@router.post("/{audit_run_id}/cancel")
async def cancel_audit_run(audit_run_id: str, payload: CancelAuditRunPayload) -> dict:
    async with SessionLocal() as session:
        result = await AuditRunApplication(session).cancel_audit_run(audit_run_id, payload.reason)
        if result is None:
            raise HTTPException(status_code=404, detail="audit run not found")
        await session.commit()
        return {"cancel_requested": True, "audit_run": result}


@router.get("/{audit_run_id}/graph")
async def audit_run_graph(audit_run_id: str) -> dict:
    return {"audit_run_id": audit_run_id, "nodes": [], "edges": [], "summary": {"status": "not_projected"}}

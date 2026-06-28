from fastapi import APIRouter, HTTPException

from dieaudit_common.persistence.base import SessionLocal
from dieaudit_common.schemas.bff import CancelAuditRunPayload, CreateAuditRunPayload, StartAuditRunPayload

from app.application.audit_runs import AuditRunApplication

router = APIRouter(prefix="/api/bff/audit-runs", tags=["audit-runs"])


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
async def start_audit_run(audit_run_id: str, payload: StartAuditRunPayload) -> dict:
    async with SessionLocal() as session:
        result = await AuditRunApplication(session).queue_audit_run(audit_run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="audit run not found")
        await session.commit()
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

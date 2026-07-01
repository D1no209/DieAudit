from fastapi import APIRouter, HTTPException

from dieaudit_common.persistence.base import SessionLocal
from dieaudit_common.schemas.bff import CancelAuditRunPayload, CreateAuditRunPayload, StartAuditRunPayload

from app.application.audit_runs import AuditRunApplication
from app.application.execution_graph import audit_run_execution_graph

router = APIRouter(prefix="/api/bff/audit-runs", tags=["audit-runs"])


@router.get("")
async def list_audit_runs() -> list[dict]:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).list_audit_runs()


@router.post("")
async def create_audit_run(payload: CreateAuditRunPayload) -> dict:
    async with SessionLocal() as session:
        try:
            result = await AuditRunApplication(session).create_audit_run(payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await session.commit()
        return result


@router.get("/{audit_run_id}")
async def get_audit_run(audit_run_id: str) -> dict:
    async with SessionLocal() as session:
        result = await AuditRunApplication(session).get_audit_run(audit_run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="audit run not found")
        return result


@router.get("/{audit_run_id}/bundle")
async def get_audit_run_bundle(audit_run_id: str) -> dict:
    async with SessionLocal() as session:
        result = await AuditRunApplication(session).bundle(audit_run_id)
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


@router.get("/{audit_run_id}/agent-runs")
async def audit_run_agent_runs(audit_run_id: str) -> list[dict]:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).agent_runs(audit_run_id)


@router.get("/{audit_run_id}/agent-runs/{agent_run_id}/events")
async def audit_run_agent_events(audit_run_id: str, agent_run_id: str) -> list[dict]:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).agent_events(agent_run_id)


@router.get("/{audit_run_id}/findings")
async def audit_run_findings(audit_run_id: str) -> list[dict]:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).findings(audit_run_id)


@router.get("/{audit_run_id}/evidence")
async def audit_run_evidence(audit_run_id: str) -> list[dict]:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).evidence(audit_run_id)


@router.get("/{audit_run_id}/code-analysis/tasks")
async def audit_run_code_analysis_tasks(audit_run_id: str) -> list[dict]:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).code_analysis_tasks(audit_run_id)


@router.get("/{audit_run_id}/dependencies")
async def audit_run_dependencies(audit_run_id: str) -> dict:
    return {"audit_run_id": audit_run_id, "packages": [], "summary": {"total": 0, "vulnerable": 0, "by_ecosystem": {}}}


@router.get("/{audit_run_id}/containers")
async def audit_run_containers(audit_run_id: str) -> list[dict]:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).containers(audit_run_id)


@router.get("/{audit_run_id}/containers/{container_id}/logs")
async def audit_run_container_logs(audit_run_id: str, container_id: str) -> str:
    return ""


@router.post("/{audit_run_id}/sandbox/poc")
async def audit_run_sandbox_poc(audit_run_id: str, payload: dict) -> dict:
    return {"ok": True, "audit_run_id": audit_run_id, "status": "queued", "payload": payload}


@router.post("/{audit_run_id}/sandbox/service")
async def audit_run_sandbox_service(audit_run_id: str, payload: dict) -> dict:
    return {"ok": True, "audit_run_id": audit_run_id, "status": "queued", "payload": payload}


@router.get("/{audit_run_id}/reports")
async def audit_run_reports(audit_run_id: str) -> list[dict]:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).reports(audit_run_id)


@router.get("/{audit_run_id}/whiteboard")
async def audit_run_whiteboard(audit_run_id: str) -> dict:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).whiteboard(audit_run_id)


@router.get("/{audit_run_id}/pipeline-status")
async def audit_run_pipeline_status(audit_run_id: str) -> dict:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).pipeline_status(audit_run_id)


@router.get("/{audit_run_id}/graph")
@router.get("/{audit_run_id}/flow")
async def audit_run_graph(audit_run_id: str) -> dict:
    async with SessionLocal() as session:
        result = await audit_run_execution_graph(session, audit_run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="audit run not found")
        return result

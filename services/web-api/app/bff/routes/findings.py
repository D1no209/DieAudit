from fastapi import APIRouter, HTTPException

from dieaudit_common.persistence.base import SessionLocal

from app.application.audit_runs import AuditRunApplication

router = APIRouter(prefix="/api/bff/findings", tags=["findings"])


@router.get("")
async def findings() -> list[dict]:
    return []


@router.get("/{finding_id}")
async def finding(finding_id: str) -> dict:
    async with SessionLocal() as session:
        result = await AuditRunApplication(session).finding(finding_id)
        if result is None:
            raise HTTPException(status_code=404, detail="finding not found")
        return result


@router.post("/{finding_id}/poc")
async def finding_poc(finding_id: str, payload: dict) -> dict:
    return {"ok": True, "finding_id": finding_id, "status": "queued", "payload": payload}

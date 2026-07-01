from fastapi import APIRouter, HTTPException

from dieaudit_common.persistence.base import SessionLocal

from app.application.agent_model_profiles import AgentModelProfileApplication

router = APIRouter(prefix="/api/bff/admin", tags=["admin"])


@router.get("/audit-events")
async def audit_events() -> list[dict]:
    return []


@router.delete("/audit-events")
async def delete_audit_events() -> dict:
    return {"ok": True, "deleted": 0}


@router.get("/api-keys")
async def api_keys() -> list[dict]:
    return []


@router.post("/api-keys")
async def create_api_key(payload: dict) -> dict:
    return {"key_id": "key-preview", "name": payload.get("name") or "API key", "scopes": payload.get("scopes") or [], "status": "active"}


@router.post("/api-keys/{key_id}/deactivate")
async def deactivate_api_key(key_id: str) -> dict:
    return {"key_id": key_id, "status": "inactive"}


@router.get("/agent-model-config")
async def agent_model_config() -> dict:
    async with SessionLocal() as session:
        return await AgentModelProfileApplication(session).get_config()


@router.put("/agent-model-config")
async def update_agent_model_config(payload: dict) -> dict:
    async with SessionLocal() as session:
        try:
            result = await AgentModelProfileApplication(session).save_config(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await session.commit()
        return result

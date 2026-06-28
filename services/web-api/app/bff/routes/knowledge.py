from fastapi import APIRouter

router = APIRouter(prefix="/api/bff/knowledge", tags=["knowledge"])


@router.get("/documents")
async def documents() -> list[dict]:
    return []


@router.get("/status")
async def status() -> dict:
    return {"ok": True, "documents": 0, "provider": "not_configured"}

from fastapi import APIRouter

router = APIRouter(prefix="/api/bff/admin", tags=["admin"])


@router.get("/audit-events")
async def audit_events() -> list[dict]:
    return []

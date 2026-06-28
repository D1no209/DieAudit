from fastapi import APIRouter

router = APIRouter(prefix="/api/bff/reports", tags=["reports"])


@router.get("")
async def reports() -> list[dict]:
    return []

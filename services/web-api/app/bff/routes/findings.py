from fastapi import APIRouter

router = APIRouter(prefix="/api/bff/findings", tags=["findings"])


@router.get("")
async def findings() -> list[dict]:
    return []

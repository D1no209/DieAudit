from fastapi import APIRouter

from app.settings import get_settings

router = APIRouter(prefix="/api/bff/session", tags=["session"])


@router.get("")
async def session() -> dict:
    settings = get_settings()
    return {
        "authenticated": False,
        "api_key_header": settings.api_key_header,
        "service": settings.service_name,
    }

from fastapi import APIRouter

router = APIRouter(prefix="/api/bff/runtime", tags=["runtime"])


@router.get("/readiness")
async def readiness() -> dict:
    return {"ok": True, "checks": [], "summary": {"status": "pass"}}


@router.get("/managed")
async def managed_runtime() -> dict:
    return {"containers": [], "networks": [], "runs": [], "summary": {"container_count": 0, "network_count": 0}}

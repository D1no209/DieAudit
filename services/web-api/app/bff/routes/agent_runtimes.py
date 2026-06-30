from __future__ import annotations

from dieaudit_common.domain.agent_runtime import enabled_agent_runtimes
from fastapi import APIRouter

router = APIRouter(prefix="/api/bff/agent-runtimes", tags=["agent-runtimes"])


@router.get("")
async def list_agent_runtimes() -> list[dict]:
    return [runtime.to_bff_dict() for runtime in enabled_agent_runtimes()]

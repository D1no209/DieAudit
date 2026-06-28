from fastapi import FastAPI

from dieaudit_common.settings import get_settings

from app.application.agent_runs import AgentRunService
from app.application.mcp_tools import McpToolService
from app.runtime.docker_client import DockerRuntimeClient

settings = get_settings()
app = FastAPI(title="DieAudit Agent Gateway", version="0.2.0")


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": settings.service_name}


@app.get("/ready")
async def ready() -> dict:
    return {"ok": True, "service": settings.service_name}


@app.get("/internal/runtime/docker/health")
async def docker_health() -> dict:
    return await DockerRuntimeClient().health()


@app.post("/internal/agent-runs")
async def start_agent_run(payload: dict) -> dict:
    return await AgentRunService().start(payload)


@app.post("/internal/tool-runs")
async def start_tool_run(payload: dict) -> dict:
    return await McpToolService().run(payload)

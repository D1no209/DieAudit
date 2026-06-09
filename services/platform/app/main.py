from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from .db import init_db
from .docker_api import DockerApiError
from .orchestrator import RuntimeOrchestrator
from .settings import get_settings
from .templates import TemplateStore


settings = get_settings()
runtime: RuntimeOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global runtime
    if settings.service_name == "web-api":
        await init_db()
    if settings.service_name in {"agent-gateway", "sandbox-runner"}:
        runtime = RuntimeOrchestrator(settings)
    yield
    if runtime:
        await runtime.close()


app = FastAPI(title=f"DieAudit {settings.service_name}", version="0.1.0", lifespan=lifespan)


class StartAgentRunRequest(BaseModel):
    audit_run_id: str = Field(default="demo-run")
    project_id: str = Field(default="demo-project")
    agent_name: str = Field(default="orchestrator")
    workspace_host_path: str | None = None
    allow_external_network: bool = False
    retain_runtime_on_failure: bool = False
    input_payload: dict[str, Any] = Field(default_factory=dict)


class TemplateBody(BaseModel):
    template: dict[str, Any]


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": settings.service_name}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    return {
        "ok": True,
        "service": settings.service_name,
        "config_root": str(settings.config_root),
        "workspace_root": str(settings.workspace_root),
        "artifact_root": str(settings.artifact_root),
    }


@app.get("/metrics")
async def metrics() -> Response:
    body = f'dieaudit_service_up{{service="{settings.service_name}"}} 1\n'
    return Response(body, media_type="text/plain; version=0.0.4")


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": "DieAudit",
        "service": settings.service_name,
        "endpoints": [
            "/health",
            "/runtime/docker/health",
            "/runtime/templates/agents",
            "/runtime/templates/mcp",
        ],
    }


@app.get("/runtime/templates/agents")
async def list_agent_templates() -> list[dict[str, Any]]:
    return TemplateStore(settings.config_root, "agent-templates").list()


@app.post("/runtime/templates/agents")
async def upsert_agent_template(body: TemplateBody) -> dict[str, Any]:
    try:
        return TemplateStore(settings.config_root, "agent-templates").upsert(body.template)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/runtime/templates/mcp")
async def list_mcp_templates() -> list[dict[str, Any]]:
    return TemplateStore(settings.config_root, "mcp-templates").list()


@app.post("/runtime/templates/mcp")
async def upsert_mcp_template(body: TemplateBody) -> dict[str, Any]:
    try:
        return TemplateStore(settings.config_root, "mcp-templates").upsert(body.template)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/runtime/docker/health")
async def docker_health() -> dict[str, Any]:
    if runtime is None:
        return await _proxy_gateway("/runtime/docker/health")
    try:
        return await runtime.docker_health()
    except DockerApiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/runtime/tool-images")
async def tool_images() -> dict[str, Any]:
    agents = TemplateStore(settings.config_root, "agent-templates").list()
    mcps = TemplateStore(settings.config_root, "mcp-templates").list()
    return {
        "agent_images": sorted({item["image"] for item in agents if "image" in item}),
        "mcp_images": sorted({item["image"] for item in mcps if "image" in item}),
    }


@app.post("/runtime/tool-images/pull")
async def pull_tool_images() -> dict[str, Any]:
    if runtime is None:
        return await _proxy_gateway("/runtime/tool-images/pull", method="POST")
    images = await tool_images()
    pulled: list[str] = []
    for image in [*images["agent_images"], *images["mcp_images"]]:
        await runtime.docker.pull_image(image)
        pulled.append(image)
    return {"pulled": pulled}


@app.post("/audit-runs/{audit_run_id}/agent-runs")
async def start_agent_run(audit_run_id: str, body: StartAgentRunRequest) -> dict[str, Any]:
    if runtime is None:
        return await _proxy_gateway(f"/audit-runs/{audit_run_id}/agent-runs", method="POST", json=body.model_dump())
    try:
        return await runtime.start_agent_run(
            audit_run_id=audit_run_id,
            project_id=body.project_id,
            agent_name=body.agent_name,
            workspace_host_path=body.workspace_host_path,
            allow_external_network=body.allow_external_network,
            retain_runtime_on_failure=body.retain_runtime_on_failure,
            input_payload=body.input_payload,
        )
    except (DockerApiError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/audit-runs/{audit_run_id}/demo")
async def start_demo(audit_run_id: str = "demo-run") -> dict[str, Any]:
    workspace = settings.workspace_root / "demo-project"
    workspace.mkdir(parents=True, exist_ok=True)
    demo_file = workspace / "app.py"
    if not demo_file.exists():
        demo_file.write_text("print('hello from vulnerable demo project')\n", encoding="utf-8")
    body = StartAgentRunRequest(
        audit_run_id=audit_run_id,
        project_id="demo-project",
        agent_name="orchestrator",
        workspace_host_path=str(workspace),
        input_payload={"goal": "run demo agent and prove MCP connectivity"},
    )
    return await start_agent_run(audit_run_id, body)


@app.get("/audit-runs/{audit_run_id}/containers")
async def audit_run_containers(audit_run_id: str) -> list[dict[str, Any]]:
    if runtime is None:
        return await _proxy_gateway(f"/audit-runs/{audit_run_id}/containers")
    return await runtime.containers(audit_run_id)


@app.get("/audit-runs/{audit_run_id}/containers/{container_id}/logs")
async def audit_run_container_logs(audit_run_id: str, container_id: str) -> Response:
    if runtime is None:
        data = await _proxy_gateway(f"/audit-runs/{audit_run_id}/containers/{container_id}/logs")
        return Response(data if isinstance(data, str) else str(data), media_type="text/plain")
    logs = await runtime.logs(container_id)
    return Response(logs, media_type="text/plain")


@app.post("/audit-runs/{audit_run_id}/cleanup")
async def cleanup_audit_run(audit_run_id: str) -> dict[str, Any]:
    if runtime is None:
        return await _proxy_gateway(f"/audit-runs/{audit_run_id}/cleanup", method="POST")
    return await runtime.cleanup_run(audit_run_id)


@app.post("/audit-runs/{audit_run_id}/validators/scale")
async def scale_validators(audit_run_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_run_id": audit_run_id,
        "requested": body,
        "status": "accepted",
        "note": "Validator scaling is represented in workflow state; dynamic container launch uses /agent-runs.",
    }


async def _proxy_gateway(path: str, *, method: str = "GET", json: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(base_url=settings.agent_gateway_url, timeout=120) as client:
        response = await client.request(method, path, json=json)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return response.json()
    return response.text

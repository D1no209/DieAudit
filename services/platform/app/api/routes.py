from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.domain.models import AgentRun, AgentRunEvent
from app.integrations.docker import DockerApiError
from app.integrations.protocols import classify_agent_protocol, fetch_a2a_agent_card, serialize_capabilities
from app.repositories import SessionLocal
from app.schemas import A2AAgentCardRequest, StartAgentRunRequest, TemplateBody, ValidatorScaleRequest
from app.services.templates import TemplateStore
from app.settings import Settings


router = APIRouter()


def register_runtime_routes(settings: Settings, runtime_provider: callable) -> APIRouter:
    async def proxy_gateway(path: str, *, method: str = "GET", json: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(base_url=settings.agent_gateway_url, timeout=120) as client:
            response = await client.request(method, path, json=json)
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    @router.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": settings.service_name}

    @router.get("/ready")
    async def ready() -> dict[str, Any]:
        return {
            "ok": True,
            "service": settings.service_name,
            "config_root": str(settings.config_root),
            "workspace_root": str(settings.workspace_root),
            "artifact_root": str(settings.artifact_root),
        }

    @router.get("/metrics")
    async def metrics() -> Response:
        body = f'dieaudit_service_up{{service="{settings.service_name}"}} 1\n'
        return Response(body, media_type="text/plain; version=0.0.4")

    @router.get("/")
    async def root() -> dict[str, Any]:
        return {
            "name": "DieAudit",
            "service": settings.service_name,
            "endpoints": [
                "/health",
                "/runtime/protocols",
                "/runtime/docker/health",
                "/runtime/templates/agents",
                "/runtime/templates/mcp",
            ],
        }

    @router.get("/runtime/protocols")
    async def runtime_protocols() -> dict[str, Any]:
        templates = TemplateStore(settings.config_root, "agent-templates").list()
        return {
            "sdk_capabilities": serialize_capabilities(),
            "agent_protocols": [classify_agent_protocol(template) for template in templates],
        }

    @router.post("/runtime/protocols/a2a/agent-card")
    async def get_a2a_agent_card(body: A2AAgentCardRequest) -> dict[str, Any]:
        try:
            return await fetch_a2a_agent_card(body.url)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/runtime/templates/agents")
    async def list_agent_templates() -> list[dict[str, Any]]:
        return TemplateStore(settings.config_root, "agent-templates").list()

    @router.post("/runtime/templates/agents")
    async def upsert_agent_template(body: TemplateBody) -> dict[str, Any]:
        try:
            return TemplateStore(settings.config_root, "agent-templates").upsert(body.template)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/runtime/templates/mcp")
    async def list_mcp_templates() -> list[dict[str, Any]]:
        return TemplateStore(settings.config_root, "mcp-templates").list()

    @router.post("/runtime/templates/mcp")
    async def upsert_mcp_template(body: TemplateBody) -> dict[str, Any]:
        try:
            return TemplateStore(settings.config_root, "mcp-templates").upsert(body.template)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/runtime/docker/health")
    async def docker_health() -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway("/runtime/docker/health")
        try:
            return await runtime.docker_health()
        except DockerApiError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/runtime/tool-images")
    async def tool_images() -> dict[str, Any]:
        agents = TemplateStore(settings.config_root, "agent-templates").list()
        mcps = TemplateStore(settings.config_root, "mcp-templates").list()
        return {
            "agent_images": sorted({item["image"] for item in agents if "image" in item}),
            "mcp_images": sorted({item["image"] for item in mcps if "image" in item}),
        }

    @router.post("/runtime/tool-images/pull")
    async def pull_tool_images() -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway("/runtime/tool-images/pull", method="POST")
        images = await tool_images()
        pulled: list[str] = []
        for image in [*images["agent_images"], *images["mcp_images"]]:
            await runtime.docker.pull_image(image)
            pulled.append(image)
        return {"pulled": pulled}

    @router.post("/audit-runs/{audit_run_id}/agent-runs")
    async def start_agent_run(audit_run_id: str, body: StartAgentRunRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/agent-runs", method="POST", json=body.model_dump())
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

    @router.post("/audit-runs/{audit_run_id}/demo")
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

    @router.post("/audit-runs/{audit_run_id}/opencode-demo")
    async def start_opencode_demo(audit_run_id: str = "opencode-demo-run") -> dict[str, Any]:
        workspace = settings.workspace_root / "opencode-demo-project"
        workspace.mkdir(parents=True, exist_ok=True)
        demo_file = workspace / "app.py"
        if not demo_file.exists():
            demo_file.write_text(
                "import os\n\n"
                "def read_profile(user_supplied_path):\n"
                "    base = '/app/profiles'\n"
                "    return open(os.path.join(base, user_supplied_path)).read()\n",
                encoding="utf-8",
            )
        body = StartAgentRunRequest(
            audit_run_id=audit_run_id,
            project_id="opencode-demo-project",
            agent_name="opencode-orchestrator",
            workspace_host_path=str(workspace),
            allow_external_network=True,
            input_payload={
                "goal": (
                    "Run a minimal code-audit pass over the demo project. Confirm you can inspect "
                    "the mounted source and report any suspicious vulnerability candidates with file paths."
                )
            },
        )
        return await start_agent_run(audit_run_id, body)

    @router.get("/audit-runs/{audit_run_id}/agent-runs")
    async def audit_run_agent_runs(audit_run_id: str) -> list[dict[str, Any]]:
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(AgentRun).where(AgentRun.audit_run_id == audit_run_id).order_by(AgentRun.created_at.desc())
                )
            ).scalars()
            return [_agent_run_to_dict(row) for row in rows]

    @router.get("/audit-runs/{audit_run_id}/agent-runs/{agent_run_id}")
    async def audit_run_agent_run(audit_run_id: str, agent_run_id: str) -> dict[str, Any]:
        async with SessionLocal() as session:
            row = await session.scalar(
                select(AgentRun).where(
                    AgentRun.audit_run_id == audit_run_id,
                    AgentRun.agent_run_id == agent_run_id,
                )
            )
            if not row:
                raise HTTPException(status_code=404, detail="agent run not found")
            return _agent_run_to_dict(row)

    @router.get("/audit-runs/{audit_run_id}/agent-runs/{agent_run_id}/events")
    async def audit_run_agent_run_events(audit_run_id: str, agent_run_id: str) -> list[dict[str, Any]]:
        async with SessionLocal() as session:
            agent_run = await session.scalar(
                select(AgentRun).where(
                    AgentRun.audit_run_id == audit_run_id,
                    AgentRun.agent_run_id == agent_run_id,
                )
            )
            if not agent_run:
                raise HTTPException(status_code=404, detail="agent run not found")
            rows = (
                await session.execute(
                    select(AgentRunEvent)
                    .where(AgentRunEvent.agent_run_id == agent_run_id)
                    .order_by(AgentRunEvent.created_at.asc())
                )
            ).scalars()
            return [
                {
                    "id": row.id,
                    "agent_run_id": row.agent_run_id,
                    "event_type": row.event_type,
                    "payload": row.payload,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    @router.get("/audit-runs/{audit_run_id}/containers")
    async def audit_run_containers(audit_run_id: str) -> list[dict[str, Any]]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/containers")
        return await runtime.containers(audit_run_id)

    @router.get("/audit-runs/{audit_run_id}/containers/{container_id}/logs")
    async def audit_run_container_logs(audit_run_id: str, container_id: str) -> Response:
        runtime = runtime_provider()
        if runtime is None:
            data = await proxy_gateway(f"/audit-runs/{audit_run_id}/containers/{container_id}/logs")
            return Response(data if isinstance(data, str) else str(data), media_type="text/plain")
        logs = await runtime.logs(container_id)
        return Response(logs, media_type="text/plain")

    @router.post("/audit-runs/{audit_run_id}/cleanup")
    async def cleanup_audit_run(audit_run_id: str) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/cleanup", method="POST")
        return await runtime.cleanup_run(audit_run_id)

    @router.post("/audit-runs/{audit_run_id}/validators/scale")
    async def scale_validators(audit_run_id: str, body: ValidatorScaleRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(
                f"/audit-runs/{audit_run_id}/validators/scale",
                method="POST",
                json=body.model_dump(),
            )
        return await runtime.scale_validators(
            audit_run_id=audit_run_id,
            project_id=body.project_id,
            findings=body.findings,
            workspace_host_path=body.workspace_host_path,
            validator_rounds=body.validator_rounds,
            max_parallel_validators=body.max_parallel_validators,
            validator_agent_name=body.validator_agent_name,
            allow_external_network=body.allow_external_network,
            retain_runtime_on_failure=body.retain_runtime_on_failure,
        )

    return router


def _agent_run_to_dict(row: AgentRun) -> dict[str, Any]:
    return {
        "agent_run_id": row.agent_run_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "agent_name": row.agent_name,
        "template_name": row.template_name,
        "protocol_kind": row.protocol_kind,
        "status": row.status,
        "input_summary": row.input_summary,
        "output_summary": row.output_summary,
        "artifact_path": row.artifact_path,
        "error": row.error,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


__all__ = ["register_runtime_routes"]

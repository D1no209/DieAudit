import json
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.domain.models import (
    AgentRun,
    AgentRunEvent,
    AuditRun,
    Evidence,
    Finding,
    Project,
    ProjectSnapshot,
    ReportArtifact,
    ValidationAttempt,
)
from app.integrations.docker import DockerApiError
from app.integrations.protocols import classify_agent_protocol, fetch_a2a_agent_card, serialize_capabilities
from app.repositories import SessionLocal
from app.schemas import (
    A2AAgentCardRequest,
    CreateAuditRunRequest,
    CreateFindingRequest,
    CreateProjectRequest,
    StartAgentRunRequest,
    TemplateBody,
    ValidatorScaleRequest,
)
from app.services.dependency_scanner import DependencyScanner
from app.services.templates import TemplateStore
from app.services.workspace import WorkspaceImportError, WorkspaceService
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

    @router.get("/projects")
    async def list_projects() -> list[dict[str, Any]]:
        async with SessionLocal() as session:
            rows = (await session.execute(select(Project).order_by(Project.created_at.desc()))).scalars()
            return [_project_to_dict(row) for row in rows]

    @router.post("/projects")
    async def create_project(body: CreateProjectRequest) -> dict[str, Any]:
        project_id = _slug_id(body.name)
        workspace = WorkspaceService(settings)
        async with SessionLocal() as session:
            existing = await session.scalar(select(Project).where(Project.project_id == project_id))
            if existing:
                raise HTTPException(status_code=409, detail="project already exists")
            project = Project(
                project_id=project_id,
                name=body.name,
                source_type="git" if body.git_url else "manual",
                source_uri=body.git_url,
                default_branch=body.ref,
                status="importing" if body.git_url else "created",
                metadata_json=body.metadata,
            )
            session.add(project)
            await session.commit()
        snapshot: dict[str, Any] | None = None
        if body.git_url:
            try:
                snapshot = workspace.import_git(project_id=project_id, git_url=body.git_url, ref=body.ref)
            except WorkspaceImportError as exc:
                await _mark_project_status(project_id, "failed", {"error": str(exc)})
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            await _record_snapshot(snapshot)
            await _mark_project_status(project_id, "ready", {"latest_snapshot_id": snapshot["snapshot_id"]})
        return {"project": await _get_project(project_id), "snapshot": snapshot}

    @router.post("/projects/upload-zip")
    async def upload_zip_project(
        name: str = Form(...),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        project_id = _slug_id(name)
        workspace = WorkspaceService(settings)
        async with SessionLocal() as session:
            existing = await session.scalar(select(Project).where(Project.project_id == project_id))
            if existing:
                raise HTTPException(status_code=409, detail="project already exists")
            project = Project(
                project_id=project_id,
                name=name,
                source_type="zip",
                source_uri=file.filename,
                status="importing",
            )
            session.add(project)
            await session.commit()
        try:
            snapshot = workspace.import_zip(project_id=project_id, filename=file.filename or "upload.zip", stream=file.file)
        except WorkspaceImportError as exc:
            await _mark_project_status(project_id, "failed", {"error": str(exc)})
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _record_snapshot(snapshot)
        await _mark_project_status(project_id, "ready", {"latest_snapshot_id": snapshot["snapshot_id"]})
        return {"project": await _get_project(project_id), "snapshot": snapshot}

    @router.get("/projects/{project_id}")
    async def get_project(project_id: str) -> dict[str, Any]:
        project = await _get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="project not found")
        return project

    @router.get("/projects/{project_id}/snapshots")
    async def list_project_snapshots(project_id: str) -> list[dict[str, Any]]:
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ProjectSnapshot)
                    .where(ProjectSnapshot.project_id == project_id)
                    .order_by(ProjectSnapshot.created_at.desc())
                )
            ).scalars()
            return [_snapshot_to_dict(row) for row in rows]

    @router.post("/projects/{project_id}/audit-runs")
    async def create_audit_run(project_id: str, body: CreateAuditRunRequest) -> dict[str, Any]:
        async with SessionLocal() as session:
            project = await session.scalar(select(Project).where(Project.project_id == project_id))
            if not project:
                raise HTTPException(status_code=404, detail="project not found")
            snapshot = await _resolve_snapshot(session, project_id, body.snapshot_id)
            audit_run_id = str(uuid.uuid4())
            audit_run = AuditRun(
                audit_run_id=audit_run_id,
                project_id=project_id,
                snapshot_id=snapshot.snapshot_id,
                status="starting" if body.start_agent else "created",
                validator_rounds=body.validator_rounds,
                max_parallel_validators=body.max_parallel_validators,
                allow_external_network=body.allow_external_network,
                retain_runtime_on_failure=body.retain_runtime_on_failure,
                config={
                    "agent_name": body.agent_name,
                    "input_payload": body.input_payload,
                    "workspace_host_path": snapshot.workspace_path,
                },
            )
            session.add(audit_run)
            await session.commit()
        agent_result = None
        if body.start_agent:
            start_body = StartAgentRunRequest(
                audit_run_id=audit_run_id,
                project_id=project_id,
                agent_name=body.agent_name,
                workspace_host_path=snapshot.workspace_path,
                allow_external_network=body.allow_external_network,
                retain_runtime_on_failure=body.retain_runtime_on_failure,
                input_payload=body.input_payload
                or {
                    "goal": "Run an initial code audit pass over the mounted project and report vulnerability candidates with file paths."
                },
            )
            agent_result = await start_agent_run(audit_run_id, start_body)
            await _mark_audit_run_status(audit_run_id, "agent_completed")
        return {"audit_run": await _get_audit_run(audit_run_id), "agent_run": agent_result}

    @router.get("/audit-runs/{audit_run_id}")
    async def get_audit_run(audit_run_id: str) -> dict[str, Any]:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        return audit_run

    @router.get("/audit-runs/{audit_run_id}/findings")
    async def list_findings(audit_run_id: str) -> list[dict[str, Any]]:
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(Finding).where(Finding.audit_run_id == audit_run_id).order_by(Finding.created_at.desc())
                )
            ).scalars()
            return [_finding_to_dict(row) for row in rows]

    @router.post("/audit-runs/{audit_run_id}/findings")
    async def create_finding(audit_run_id: str, body: CreateFindingRequest) -> dict[str, Any]:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        finding = Finding(
            finding_id=str(uuid.uuid4()),
            audit_run_id=audit_run_id,
            project_id=audit_run["project_id"],
            title=body.title,
            severity=body.severity,
            status=body.status,
            file_path=body.file_path,
            line_start=body.line_start,
            line_end=body.line_end,
            rule_id=body.rule_id,
            description=body.description,
            source=body.source,
            raw=body.raw,
        )
        async with SessionLocal() as session:
            session.add(finding)
            await session.commit()
            return _finding_to_dict(finding)

    @router.post("/audit-runs/{audit_run_id}/sca")
    async def run_sca(audit_run_id: str) -> dict[str, Any]:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        if not workspace_path:
            raise HTTPException(status_code=400, detail="audit run has no workspace path")
        try:
            result = await DependencyScanner(workspace_path).scan_osv()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        created = []
        async with SessionLocal() as session:
            for item in result["findings"]:
                finding = Finding(
                    finding_id=str(uuid.uuid4()),
                    audit_run_id=audit_run_id,
                    project_id=audit_run["project_id"],
                    title=item["title"],
                    severity=item["severity"],
                    status=item["status"],
                    file_path=item.get("file_path"),
                    line_start=item.get("line_start"),
                    line_end=item.get("line_end"),
                    rule_id=item.get("rule_id"),
                    description=item.get("description"),
                    source=item.get("source", "sca-osv"),
                    raw=item.get("raw", {}),
                )
                session.add(finding)
                created.append(finding)
            await session.commit()
            return {
                "audit_run_id": audit_run_id,
                "packages": result["packages"],
                "vulnerabilities": result["vulnerabilities"],
                "findings": [_finding_to_dict(row) for row in created],
            }

    @router.post("/audit-runs/{audit_run_id}/run-pipeline")
    async def run_pipeline(audit_run_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/run-pipeline", method="POST")
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        if not workspace_path:
            raise HTTPException(status_code=400, detail="audit run has no workspace path")
        await _mark_audit_run_status(audit_run_id, "queued")
        background_tasks.add_task(_execute_pipeline, audit_run_id, settings, runtime)
        return {"audit_run_id": audit_run_id, "status": "accepted"}

    async def _execute_pipeline(audit_run_id: str, settings: Settings, runtime) -> None:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            return
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        if not workspace_path:
            await _mark_audit_run_status(audit_run_id, "failed")
            return
        await _mark_audit_run_status(audit_run_id, "running")
        steps: list[dict[str, Any]] = []
        try:
            agent_result = await runtime.start_agent_run(
                audit_run_id=audit_run_id,
                project_id=audit_run["project_id"],
                agent_name=audit_run.get("config", {}).get("agent_name") or "opencode-orchestrator",
                workspace_host_path=workspace_path,
                allow_external_network=audit_run["allow_external_network"],
                retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
                input_payload=audit_run.get("config", {}).get("input_payload")
                or {
                    "goal": (
                        "Run a structured security audit pass. Return JSON with summary, findings, and evidence. "
                        "Every finding must include title, severity, file_path, line_start, description, confidence, and source."
                    )
                },
            )
            steps.append({"step": "agent-audit", "result": agent_result})

            try:
                sca_result = await _run_sca_mcp(audit_run_id, audit_run["project_id"], workspace_path, runtime, audit_run)
            except Exception as exc:
                sca_result = {"ok": False, "error": str(exc)}
                await _record_pipeline_event(audit_run_id, "sca_failed", sca_result)
            steps.append({"step": "sca", "result": sca_result})

            try:
                semgrep_result = await _run_semgrep_mcp(audit_run_id, audit_run["project_id"], workspace_path, runtime, audit_run)
            except Exception as exc:
                semgrep_result = {"ok": False, "error": str(exc)}
                await _record_pipeline_event(audit_run_id, "semgrep_failed", semgrep_result)
            steps.append({"step": "semgrep", "result": semgrep_result})

            findings = await _list_findings(audit_run_id)
            validator_result = await runtime.scale_validators(
                audit_run_id=audit_run_id,
                project_id=audit_run["project_id"],
                findings=findings,
                workspace_host_path=workspace_path,
                validator_rounds=audit_run["validator_rounds"],
                max_parallel_validators=audit_run["max_parallel_validators"],
                validator_agent_name="opencode-validator",
                allow_external_network=audit_run["allow_external_network"],
                retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
                wait_for_completion=True,
            )
            steps.append({"step": "validators", "result": validator_result})

            judge_result = await _judge_audit_run_internal(audit_run_id, runtime)
            report_result = await _generate_report_internal(audit_run_id, settings)
            await _record_pipeline_summary(audit_run_id, {"steps": steps, "judge": judge_result, "report": report_result})
            await _mark_audit_run_status(audit_run_id, "completed")
        except Exception as exc:
            await _record_pipeline_event(audit_run_id, "pipeline_failed", {"error": str(exc), "steps": steps})
            await _mark_audit_run_status(audit_run_id, "failed")

    @router.post("/audit-runs/{audit_run_id}/judge")
    async def judge_audit_run(audit_run_id: str) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/judge", method="POST")
        result = await _judge_audit_run_internal(audit_run_id, runtime)
        if result.get("missing"):
            raise HTTPException(status_code=404, detail="audit run not found")
        return result

    @router.post("/audit-runs/{audit_run_id}/report")
    async def generate_report(audit_run_id: str) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/report", method="POST")
        result = await _generate_report_internal(audit_run_id, settings)
        if result.get("missing"):
            raise HTTPException(status_code=404, detail="audit run not found")
        return result

    @router.get("/audit-runs/{audit_run_id}/evidence")
    async def audit_run_evidence(audit_run_id: str) -> list[dict[str, Any]]:
        return await _list_evidence(audit_run_id)

    @router.get("/audit-runs/{audit_run_id}/validation-attempts")
    async def audit_run_validation_attempts(audit_run_id: str) -> list[dict[str, Any]]:
        return await _list_validation_attempts(audit_run_id)

    @router.get("/audit-runs/{audit_run_id}/reports")
    async def audit_run_reports(audit_run_id: str) -> list[dict[str, Any]]:
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ReportArtifact)
                    .where(ReportArtifact.audit_run_id == audit_run_id)
                    .order_by(ReportArtifact.created_at.desc())
                )
            ).scalars()
            return [_report_to_dict(row) for row in rows]

    @router.get("/reports/{report_id}/download")
    async def download_report(report_id: str) -> FileResponse:
        async with SessionLocal() as session:
            report = await session.scalar(select(ReportArtifact).where(ReportArtifact.report_id == report_id))
            if not report:
                raise HTTPException(status_code=404, detail="report not found")
            path = Path(report.path)
            if not path.exists():
                raise HTTPException(status_code=404, detail="report artifact not found")
            return FileResponse(path, filename=path.name, media_type="text/markdown")

    @router.get("/findings/{finding_id}")
    async def get_finding(finding_id: str) -> dict[str, Any]:
        async with SessionLocal() as session:
            finding = await session.scalar(select(Finding).where(Finding.finding_id == finding_id))
            if not finding:
                raise HTTPException(status_code=404, detail="finding not found")
            evidence_rows = (
                await session.execute(select(Evidence).where(Evidence.finding_id == finding_id).order_by(Evidence.created_at.asc()))
            ).scalars()
            attempt_rows = (
                await session.execute(
                    select(ValidationAttempt)
                    .where(ValidationAttempt.finding_id == finding_id)
                    .order_by(ValidationAttempt.round_index.asc())
                )
            ).scalars()
            return {
                "finding": _finding_to_dict(finding),
                "evidence": [_evidence_to_dict(row) for row in evidence_rows],
                "validation_attempts": [_attempt_to_dict(row) for row in attempt_rows],
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
            wait_for_completion=body.wait_for_completion,
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


def _project_to_dict(row: Project) -> dict[str, Any]:
    return {
        "project_id": row.project_id,
        "name": row.name,
        "source_type": row.source_type,
        "source_uri": row.source_uri,
        "default_branch": row.default_branch,
        "status": row.status,
        "metadata": row.metadata_json,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _snapshot_to_dict(row: ProjectSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": row.snapshot_id,
        "project_id": row.project_id,
        "source_type": row.source_type,
        "source_ref": row.source_ref,
        "workspace_path": row.workspace_path,
        "artifact_path": row.artifact_path,
        "content_hash": row.content_hash,
        "status": row.status,
        "metadata": row.metadata_json,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _audit_run_to_dict(row: AuditRun) -> dict[str, Any]:
    return {
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "snapshot_id": row.snapshot_id,
        "status": row.status,
        "validator_rounds": row.validator_rounds,
        "max_parallel_validators": row.max_parallel_validators,
        "allow_external_network": row.allow_external_network,
        "retain_runtime_on_failure": row.retain_runtime_on_failure,
        "config": row.config,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _finding_to_dict(row: Finding) -> dict[str, Any]:
    return {
        "finding_id": row.finding_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "title": row.title,
        "severity": row.severity,
        "status": row.status,
        "file_path": row.file_path,
        "line_start": row.line_start,
        "line_end": row.line_end,
        "rule_id": row.rule_id,
        "description": row.description,
        "source": row.source,
        "raw": row.raw,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _evidence_to_dict(row: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": row.evidence_id,
        "finding_id": row.finding_id,
        "audit_run_id": row.audit_run_id,
        "kind": row.kind,
        "summary": row.summary,
        "artifact_path": row.artifact_path,
        "payload": row.payload,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _attempt_to_dict(row: ValidationAttempt) -> dict[str, Any]:
    return {
        "attempt_id": row.attempt_id,
        "finding_id": row.finding_id,
        "audit_run_id": row.audit_run_id,
        "agent_run_id": row.agent_run_id,
        "round_index": row.round_index,
        "status": row.status,
        "result": row.result,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _report_to_dict(row: ReportArtifact) -> dict[str, Any]:
    return {
        "report_id": row.report_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "kind": row.kind,
        "path": row.path,
        "summary": row.summary,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


async def _record_snapshot(snapshot: dict[str, Any]) -> None:
    async with SessionLocal() as session:
        session.add(
            ProjectSnapshot(
                snapshot_id=snapshot["snapshot_id"],
                project_id=snapshot["project_id"],
                source_type=snapshot["source_type"],
                source_ref=snapshot.get("source_ref"),
                workspace_path=snapshot["workspace_path"],
                artifact_path=snapshot.get("artifact_path"),
                content_hash=snapshot.get("content_hash"),
                status="ready",
                metadata_json={},
            )
        )
        await session.commit()


async def _mark_project_status(project_id: str, status: str, metadata_update: dict[str, Any] | None = None) -> None:
    async with SessionLocal() as session:
        project = await session.scalar(select(Project).where(Project.project_id == project_id))
        if not project:
            return
        project.status = status
        if metadata_update:
            project.metadata_json = {**(project.metadata_json or {}), **metadata_update}
        await session.commit()


async def _mark_audit_run_status(audit_run_id: str, status: str) -> None:
    async with SessionLocal() as session:
        audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
        if audit_run:
            audit_run.status = status
            await session.commit()


async def _get_project(project_id: str) -> dict[str, Any] | None:
    async with SessionLocal() as session:
        project = await session.scalar(select(Project).where(Project.project_id == project_id))
        return _project_to_dict(project) if project else None


async def _get_audit_run(audit_run_id: str) -> dict[str, Any] | None:
    async with SessionLocal() as session:
        audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
        return _audit_run_to_dict(audit_run) if audit_run else None


async def _list_findings(audit_run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(Finding).where(Finding.audit_run_id == audit_run_id).order_by(Finding.created_at.asc()))
        ).scalars()
        return [_finding_to_dict(row) for row in rows]


async def _list_evidence(audit_run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(Evidence).where(Evidence.audit_run_id == audit_run_id).order_by(Evidence.created_at.asc()))
        ).scalars()
        return [_evidence_to_dict(row) for row in rows]


async def _list_validation_attempts(audit_run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(ValidationAttempt)
                .where(ValidationAttempt.audit_run_id == audit_run_id)
                .order_by(ValidationAttempt.created_at.asc())
            )
        ).scalars()
        return [_attempt_to_dict(row) for row in rows]


async def _list_agent_runs(audit_run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(AgentRun).where(AgentRun.audit_run_id == audit_run_id).order_by(AgentRun.created_at.asc()))
        ).scalars()
        return [_agent_run_to_dict(row) for row in rows]


async def _record_pipeline_event(audit_run_id: str, event_type: str, payload: dict[str, Any]) -> None:
    async with SessionLocal() as session:
        agent_run = await session.scalar(
            select(AgentRun).where(AgentRun.audit_run_id == audit_run_id).order_by(AgentRun.created_at.desc())
        )
        if agent_run:
            session.add(AgentRunEvent(agent_run_id=agent_run.agent_run_id, event_type=event_type, payload=payload))
            await session.commit()


async def _record_pipeline_summary(audit_run_id: str, summary: dict[str, Any]) -> None:
    async with SessionLocal() as session:
        audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
        if not audit_run:
            return
        config = dict(audit_run.config or {})
        config["pipeline"] = summary
        audit_run.config = config
        agent_run = await session.scalar(
            select(AgentRun).where(AgentRun.audit_run_id == audit_run_id).order_by(AgentRun.created_at.desc())
        )
        if agent_run:
            session.add(AgentRunEvent(agent_run_id=agent_run.agent_run_id, event_type="pipeline_summary", payload=summary))
        await session.commit()


async def _run_sca_mcp(
    audit_run_id: str,
    project_id: str,
    workspace_path: str,
    runtime: Any,
    audit_run: dict[str, Any],
) -> dict[str, Any]:
    allow_network = bool(audit_run.get("config", {}).get("allow_sca_external_network", True))
    sbom_result: dict[str, Any] | None = None
    try:
        sbom_result = await runtime.run_mcp_tool(
            audit_run_id=audit_run_id,
            project_id=project_id,
            mcp_name="sca-mcp",
            tool_path="/tools/generate_sbom",
            workspace_host_path=workspace_path,
            payload={"output_format": "spdx-json", "timeout_seconds": 300},
            allow_external_network=allow_network,
            retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
        )
    except Exception as exc:
        sbom_result = {"ok": False, "error": str(exc)}
        await _record_pipeline_event(audit_run_id, "sca_sbom_failed", sbom_result)

    osv_result = await runtime.run_mcp_tool(
        audit_run_id=audit_run_id,
        project_id=project_id,
        mcp_name="sca-mcp",
        tool_path="/tools/query_osv",
        workspace_host_path=workspace_path,
        payload={"max_packages": int(audit_run.get("config", {}).get("sca_max_packages", 200))},
        allow_external_network=allow_network,
        retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
    )
    result = osv_result.get("result", {})
    artifact_path = None
    if isinstance(sbom_result, dict):
        artifact_path = ((sbom_result.get("result") or {}).get("artifact_path") if sbom_result.get("result") else None)
    created = await _ingest_tool_findings(
        audit_run_id=audit_run_id,
        project_id=project_id,
        source="sca-mcp",
        findings=result.get("findings", []) if isinstance(result, dict) else [],
        evidence_kind="sca-result",
        artifact_path=artifact_path,
    )
    summary = {
        "ok": bool(osv_result.get("ok")),
        "packages": len(result.get("packages", [])) if isinstance(result, dict) else 0,
        "vulnerabilities": len(result.get("vulnerabilities", [])) if isinstance(result, dict) else 0,
        "findings_created": created,
        "sbom": sbom_result,
    }
    await _record_pipeline_event(audit_run_id, "sca_completed", summary)
    return summary


async def _run_semgrep_mcp(
    audit_run_id: str,
    project_id: str,
    workspace_path: str,
    runtime: Any,
    audit_run: dict[str, Any],
) -> dict[str, Any]:
    mcp_result = await runtime.run_mcp_tool(
        audit_run_id=audit_run_id,
        project_id=project_id,
        mcp_name="semgrep-mcp",
        tool_path="/tools/semgrep_scan",
        workspace_host_path=workspace_path,
        payload={"config": "auto", "output_format": "json", "timeout_seconds": 300},
        allow_external_network=False,
        retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
    )
    result = mcp_result.get("result", {})
    created = await _ingest_tool_findings(
        audit_run_id=audit_run_id,
        project_id=project_id,
        source="semgrep-mcp",
        findings=result.get("findings", []) if isinstance(result, dict) else [],
        evidence_kind="semgrep-result",
        artifact_path=result.get("artifact_path") if isinstance(result, dict) else None,
    )
    summary = {
        "ok": bool(result.get("ok")) if isinstance(result, dict) else bool(mcp_result.get("ok")),
        "available": result.get("available") if isinstance(result, dict) else None,
        "artifact_path": result.get("artifact_path") if isinstance(result, dict) else None,
        "findings_created": created,
    }
    await _record_pipeline_event(audit_run_id, "semgrep_completed", summary)
    return summary


async def _ingest_tool_findings(
    *,
    audit_run_id: str,
    project_id: str,
    source: str,
    findings: list[Any],
    evidence_kind: str,
    artifact_path: str | None = None,
) -> int:
    created = 0
    async with SessionLocal() as session:
        for item in findings:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("rule_id") or f"{source} finding")[:255]
            finding = Finding(
                finding_id=str(uuid.uuid4()),
                audit_run_id=audit_run_id,
                project_id=project_id,
                title=title,
                severity=str(item.get("severity") or "unknown").lower(),
                status=str(item.get("status") or "candidate"),
                file_path=str(item["file_path"]) if item.get("file_path") else None,
                line_start=_optional_int(item.get("line_start")),
                line_end=_optional_int(item.get("line_end")),
                rule_id=str(item["rule_id"]) if item.get("rule_id") else None,
                description=str(item["description"]) if item.get("description") else None,
                source=str(item.get("source") or source),
                raw=item,
            )
            session.add(finding)
            session.add(
                Evidence(
                    evidence_id=str(uuid.uuid4()),
                    finding_id=finding.finding_id,
                    audit_run_id=audit_run_id,
                    kind=evidence_kind,
                    summary=finding.description or finding.title,
                    artifact_path=artifact_path,
                    payload=item,
                )
            )
            created += 1
        await session.commit()
    return created


async def _judge_audit_run_internal(audit_run_id: str, runtime: Any) -> dict[str, Any]:
    audit_run = await _get_audit_run(audit_run_id)
    if not audit_run:
        return {"missing": True}
    workspace_path = audit_run.get("config", {}).get("workspace_host_path")
    findings = await _list_findings(audit_run_id)
    evidence = await _list_evidence(audit_run_id)
    attempts = await _list_validation_attempts(audit_run_id)
    agent_result: dict[str, Any] | None = None
    parsed_decisions: list[dict[str, Any]] = []
    if findings and workspace_path:
        try:
            agent_result = await runtime.start_agent_run(
                audit_run_id=audit_run_id,
                project_id=audit_run["project_id"],
                agent_name="opencode-judger",
                workspace_host_path=workspace_path,
                allow_external_network=audit_run["allow_external_network"],
                retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
                input_payload={
                    "goal": (
                        "Judge the audit findings. Return JSON with decisions: "
                        "[{\"finding_id\":\"...\",\"status\":\"confirmed|false_positive|needs_review\",\"reason\":\"...\"}]."
                    ),
                    "findings": findings,
                    "evidence": evidence,
                    "validation_attempts": attempts,
                },
            )
            agent_run_id = str(agent_result.get("agent_run_id") or agent_result.get("run_id") or "")
            if agent_run_id:
                parsed_decisions = await _extract_judger_decisions(agent_run_id)
        except Exception as exc:
            agent_result = {"ok": False, "error": str(exc)}
            await _record_pipeline_event(audit_run_id, "judger_failed", agent_result)
    decisions = await _apply_judgement(audit_run_id, parsed_decisions)
    result = {"audit_run_id": audit_run_id, "agent_run": agent_result, "decisions": decisions}
    await _record_pipeline_event(audit_run_id, "judgement_completed", result)
    return result


async def _generate_report_internal(audit_run_id: str, settings: Settings) -> dict[str, Any]:
    audit_run = await _get_audit_run(audit_run_id)
    if not audit_run:
        return {"missing": True}
    findings = await _list_findings(audit_run_id)
    evidence = await _list_evidence(audit_run_id)
    attempts = await _list_validation_attempts(audit_run_id)
    agent_runs = await _list_agent_runs(audit_run_id)
    payload = {
        "audit_run": audit_run,
        "findings": findings,
        "evidence": evidence,
        "validation_attempts": attempts,
        "agent_runs": agent_runs,
    }
    report_id = str(uuid.uuid4())
    report_dir = settings.artifact_root / "reports" / audit_run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = report_dir / f"{report_id}.md"
    json_path = report_dir / f"{report_id}.json"
    markdown_path.write_text(_report_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    summary = {
        "finding_count": len(findings),
        "evidence_count": len(evidence),
        "validation_attempt_count": len(attempts),
        "json_path": str(json_path),
    }
    async with SessionLocal() as session:
        session.add(
            ReportArtifact(
                report_id=report_id,
                audit_run_id=audit_run_id,
                project_id=audit_run["project_id"],
                kind="markdown",
                path=str(markdown_path),
                summary=summary,
            )
        )
        await session.commit()
    result = {"report_id": report_id, "markdown_path": str(markdown_path), "json_path": str(json_path), "summary": summary}
    await _record_pipeline_event(audit_run_id, "report_generated", result)
    return result


async def _run_semgrep_best_effort(
    audit_run_id: str,
    project_id: str,
    workspace_path: str,
    settings: Settings,
) -> dict[str, Any]:
    import shutil
    import subprocess

    semgrep = shutil.which("semgrep")
    if not semgrep:
        result = {"ok": False, "available": False, "error": "semgrep executable is not installed in web-api container"}
        await _record_pipeline_event(audit_run_id, "semgrep_skipped", result)
        return result
    artifact_dir = settings.artifact_root / "semgrep" / audit_run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    output_path = artifact_dir / "semgrep-results.json"
    command = [semgrep, "scan", "--config", "auto", "--json", "--output", str(output_path), workspace_path]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if completed.returncode not in {0, 1}:
        result = {
            "ok": False,
            "available": True,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
        await _record_pipeline_event(audit_run_id, "semgrep_failed", result)
        return result
    data = json.loads(output_path.read_text(encoding="utf-8", errors="replace")) if output_path.exists() else {}
    created = []
    async with SessionLocal() as session:
        for item in data.get("results", []) or []:
            extra = item.get("extra", {}) or {}
            finding = Finding(
                finding_id=str(uuid.uuid4()),
                audit_run_id=audit_run_id,
                project_id=project_id,
                title=str(extra.get("message") or item.get("check_id") or "Semgrep finding")[:255],
                severity=str(extra.get("severity") or "unknown").lower(),
                status="candidate",
                file_path=item.get("path"),
                line_start=(item.get("start") or {}).get("line"),
                line_end=(item.get("end") or {}).get("line"),
                rule_id=item.get("check_id"),
                description=extra.get("message"),
                source="semgrep",
                raw=item,
            )
            session.add(finding)
            created.append(finding)
            session.add(
                Evidence(
                    evidence_id=str(uuid.uuid4()),
                    finding_id=finding.finding_id,
                    audit_run_id=audit_run_id,
                    kind="semgrep-result",
                    summary=extra.get("message"),
                    artifact_path=str(output_path),
                    payload=item,
                )
            )
        await session.commit()
    return {"ok": True, "available": True, "artifact_path": str(output_path), "findings_created": len(created)}


async def _extract_judger_decisions(agent_run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        agent_run = await session.scalar(select(AgentRun).where(AgentRun.agent_run_id == agent_run_id))
        if not agent_run:
            return []
        payload = agent_run.output_summary or {}
    for candidate in _walk_values(payload):
        parsed = None
        if isinstance(candidate, dict) and ("decisions" in candidate or "findings" in candidate):
            parsed = candidate
        elif isinstance(candidate, str) and ("decisions" in candidate or "finding_id" in candidate):
            parsed = _parse_json_object(candidate)
        if not isinstance(parsed, dict):
            continue
        decisions = parsed.get("decisions") or parsed.get("findings")
        if isinstance(decisions, list):
            return [item for item in decisions if isinstance(item, dict)]
    return []


def _walk_values(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    candidates = [stripped]
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first >= 0 and last > first:
        candidates.append(stripped[first : last + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


async def _apply_judgement(audit_run_id: str, structured_decisions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    allowed_statuses = {"confirmed", "false_positive", "needs_review"}
    structured_by_id: dict[str, dict[str, Any]] = {}
    for decision in structured_decisions or []:
        finding_id = str(decision.get("finding_id") or decision.get("id") or "")
        status = str(decision.get("status") or decision.get("judgement") or "").lower()
        if finding_id and status in allowed_statuses:
            structured_by_id[finding_id] = decision
    async with SessionLocal() as session:
        findings = (
            await session.execute(select(Finding).where(Finding.audit_run_id == audit_run_id).order_by(Finding.created_at.asc()))
        ).scalars()
        decisions = []
        for finding in findings:
            structured = structured_by_id.get(finding.finding_id)
            if structured:
                status = str(structured.get("status") or structured.get("judgement")).lower()
                finding.status = status
                decisions.append(
                    {
                        "finding_id": finding.finding_id,
                        "status": status,
                        "source": "judger-agent",
                        "reason": structured.get("reason") or structured.get("description") or structured.get("rationale"),
                    }
                )
                continue
            attempts = (
                await session.execute(
                    select(ValidationAttempt).where(
                        ValidationAttempt.audit_run_id == audit_run_id,
                        ValidationAttempt.finding_id == finding.finding_id,
                    )
                )
            ).scalars()
            attempt_rows = list(attempts)
            completed = [item for item in attempt_rows if item.status == "completed"]
            failed = [item for item in attempt_rows if item.status == "failed"]
            if completed:
                status = "confirmed"
            elif failed:
                status = "needs_review"
            else:
                status = "needs_review" if finding.status in {"candidate", "validating"} else finding.status
            finding.status = status
            decisions.append(
                {
                    "finding_id": finding.finding_id,
                    "status": status,
                    "source": "rule-fallback",
                    "completed_attempts": len(completed),
                    "failed_attempts": len(failed),
                }
            )
        await session.commit()
        return decisions


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _report_markdown(payload: dict[str, Any]) -> str:
    audit_run = payload["audit_run"]
    findings = payload["findings"]
    attempts = payload["validation_attempts"]
    evidence = payload["evidence"]
    lines = [
        f"# DieAudit Report {audit_run['audit_run_id']}",
        "",
        f"- Project: `{audit_run['project_id']}`",
        f"- Snapshot: `{audit_run.get('snapshot_id') or '-'}`",
        f"- Status: `{audit_run['status']}`",
        f"- Findings: `{len(findings)}`",
        f"- Evidence: `{len(evidence)}`",
        f"- Validation attempts: `{len(attempts)}`",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("No findings were recorded.")
    for finding in findings:
        lines.extend(
            [
                f"### {finding['title']}",
                "",
                f"- ID: `{finding['finding_id']}`",
                f"- Severity: `{finding['severity']}`",
                f"- Status: `{finding['status']}`",
                f"- Location: `{finding.get('file_path') or '-'}`:{finding.get('line_start') or '-'}",
                f"- Source: `{finding['source']}`",
                "",
                finding.get("description") or "",
                "",
            ]
        )
    return "\n".join(lines)


async def _resolve_snapshot(session, project_id: str, snapshot_id: str | None) -> ProjectSnapshot:
    query = select(ProjectSnapshot).where(ProjectSnapshot.project_id == project_id)
    if snapshot_id:
        query = query.where(ProjectSnapshot.snapshot_id == snapshot_id)
    else:
        query = query.order_by(ProjectSnapshot.created_at.desc())
    snapshot = await session.scalar(query)
    if not snapshot:
        raise HTTPException(status_code=400, detail="project has no snapshot")
    return snapshot


def _slug_id(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    slug = "-".join(part for part in slug.split("-") if part)
    return slug[:80] or str(uuid.uuid4())


__all__ = ["register_runtime_routes"]

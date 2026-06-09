import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.domain.models import (
    AgentRun,
    AgentRunEvent,
    AuditRun,
    AuditRunEvent,
    Evidence,
    Finding,
    PlatformAuditEvent,
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
    RunPocRequest,
    StartAgentRunRequest,
    StartSandboxServiceRequest,
    TemplateBody,
    ValidatorScaleRequest,
)
from app.services.dependency_scanner import DependencyScanner
from app.services.templates import TemplateStore
from app.services.workspace import WorkspaceImportError, WorkspaceService
from app.settings import Settings


router = APIRouter()


class PipelineCancelled(RuntimeError):
    pass


def register_runtime_routes(settings: Settings, runtime_provider: callable) -> APIRouter:
    async def proxy_gateway(path: str, *, method: str = "GET", json: dict[str, Any] | None = None) -> Any:
        headers = {}
        if settings.dieaudit_api_key:
            headers[settings.api_key_header] = settings.dieaudit_api_key
        async with httpx.AsyncClient(base_url=settings.agent_gateway_url, timeout=120) as client:
            response = await client.request(method, path, json=json, headers=headers)
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
        await _clear_pipeline_cancel(audit_run_id)
        await _mark_audit_run_status(audit_run_id, "queued")
        await _set_pipeline_state(audit_run_id, stage="queued", status="queued")
        await _record_audit_run_event(audit_run_id, "pipeline_queued", {"status": "queued"})
        background_tasks.add_task(_execute_pipeline, audit_run_id, settings, runtime)
        return {"audit_run_id": audit_run_id, "status": "accepted"}

    @router.post("/audit-runs/{audit_run_id}/cancel")
    async def cancel_audit_run(audit_run_id: str) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/cancel", method="POST")
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        await _request_pipeline_cancel(audit_run_id, reason="user_requested")
        await _mark_audit_run_status(audit_run_id, "cancelling")
        await _set_pipeline_state(audit_run_id, stage="cancelling", status="cancelling")
        await _record_audit_run_event(audit_run_id, "cancel_requested", {"reason": "user_requested"})
        cleanup_result: dict[str, Any] | None = None
        cleanup_error: str | None = None
        try:
            cleanup_result = await runtime.cleanup_run(audit_run_id)
        except Exception as exc:
            cleanup_error = str(exc)
            await _record_audit_run_event(audit_run_id, "cancel_cleanup_failed", {"error": cleanup_error})
        final_status = "cancelling"
        removed_container_count = len((cleanup_result or {}).get("removed_containers") or [])
        if removed_container_count == 0 or not _is_active_audit_status(audit_run["status"]):
            final_status = "cancelled"
            await _mark_audit_run_status(audit_run_id, "cancelled")
            await _set_pipeline_state(audit_run_id, stage="cancelled", status="cancelled", error="user_requested")
            await _record_audit_run_event(audit_run_id, "pipeline_cancelled", {"reason": "user_requested"})
        return {
            "audit_run_id": audit_run_id,
            "status": final_status,
            "cleanup": cleanup_result,
            "cleanup_error": cleanup_error,
        }

    async def _execute_pipeline(audit_run_id: str, settings: Settings, runtime) -> None:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            return
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        if not workspace_path:
            await _mark_audit_run_status(audit_run_id, "failed")
            await _set_pipeline_state(audit_run_id, stage="failed", status="failed", error="audit run has no workspace path")
            await _record_audit_run_event(audit_run_id, "pipeline_failed", {"error": "audit run has no workspace path"})
            return
        await _mark_audit_run_status(audit_run_id, "running")
        await _set_pipeline_state(audit_run_id, stage="agent-audit", status="running")
        await _record_audit_run_event(audit_run_id, "pipeline_started", {"stage": "agent-audit"})
        steps: list[dict[str, Any]] = []
        try:
            await _raise_if_cancelled(audit_run_id)
            await _record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "agent-audit"})
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
            await _record_audit_run_event(audit_run_id, "pipeline_step_completed", {"step": "agent-audit", "result": _compact_event_payload(agent_result)})
            await _raise_if_cancelled(audit_run_id)

            await _set_pipeline_state(audit_run_id, stage="sca", status="running")
            await _record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "sca"})
            try:
                sca_result = await _run_sca_mcp(audit_run_id, audit_run["project_id"], workspace_path, runtime, audit_run)
            except Exception as exc:
                sca_result = {"ok": False, "error": str(exc)}
                await _record_pipeline_event(audit_run_id, "sca_failed", sca_result)
            steps.append({"step": "sca", "result": sca_result})
            await _record_audit_run_event(audit_run_id, "pipeline_step_completed", {"step": "sca", "result": _compact_event_payload(sca_result)})
            await _raise_if_cancelled(audit_run_id)

            await _set_pipeline_state(audit_run_id, stage="semgrep", status="running")
            await _record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "semgrep"})
            try:
                semgrep_result = await _run_semgrep_mcp(audit_run_id, audit_run["project_id"], workspace_path, runtime, audit_run)
            except Exception as exc:
                semgrep_result = {"ok": False, "error": str(exc)}
                await _record_pipeline_event(audit_run_id, "semgrep_failed", semgrep_result)
            steps.append({"step": "semgrep", "result": semgrep_result})
            await _record_audit_run_event(audit_run_id, "pipeline_step_completed", {"step": "semgrep", "result": _compact_event_payload(semgrep_result)})
            await _raise_if_cancelled(audit_run_id)

            findings = await _list_findings(audit_run_id)
            await _set_pipeline_state(audit_run_id, stage="validators", status="running")
            await _record_audit_run_event(
                audit_run_id,
                "pipeline_step_started",
                {"step": "validators", "finding_count": len(findings), "validator_rounds": audit_run["validator_rounds"]},
            )
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
            await _record_audit_run_event(audit_run_id, "pipeline_step_completed", {"step": "validators", "result": _compact_event_payload(validator_result)})
            await _raise_if_cancelled(audit_run_id)

            await _set_pipeline_state(audit_run_id, stage="judgement", status="running")
            await _record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "judgement"})
            judge_result = await _judge_audit_run_internal(audit_run_id, runtime)
            await _record_audit_run_event(audit_run_id, "pipeline_step_completed", {"step": "judgement", "result": _compact_event_payload(judge_result)})
            await _raise_if_cancelled(audit_run_id)
            await _set_pipeline_state(audit_run_id, stage="report", status="running")
            await _record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "report"})
            report_result = await _generate_report_internal(audit_run_id, settings)
            await _record_audit_run_event(audit_run_id, "pipeline_step_completed", {"step": "report", "result": _compact_event_payload(report_result)})
            await _record_pipeline_summary(audit_run_id, {"steps": steps, "judge": judge_result, "report": report_result})
            await _mark_audit_run_status(audit_run_id, "completed")
            await _set_pipeline_state(audit_run_id, stage="completed", status="completed")
            await _record_audit_run_event(audit_run_id, "pipeline_completed", {"report": _compact_event_payload(report_result)})
        except PipelineCancelled as exc:
            await _mark_audit_run_status(audit_run_id, "cancelled")
            await _set_pipeline_state(audit_run_id, stage="cancelled", status="cancelled", error=str(exc))
            await _record_audit_run_event(audit_run_id, "pipeline_cancelled", {"reason": str(exc), "steps": [_compact_event_payload(step) for step in steps]})
        except Exception as exc:
            if await _is_cancel_requested(audit_run_id):
                reason = await _cancel_reason(audit_run_id)
                await _mark_audit_run_status(audit_run_id, "cancelled")
                await _set_pipeline_state(audit_run_id, stage="cancelled", status="cancelled", error=reason or str(exc))
                await _record_audit_run_event(
                    audit_run_id,
                    "pipeline_cancelled",
                    {"reason": reason or str(exc), "error": str(exc), "steps": [_compact_event_payload(step) for step in steps]},
                )
                return
            await _record_pipeline_event(audit_run_id, "pipeline_failed", {"error": str(exc), "steps": steps})
            await _set_pipeline_state(audit_run_id, stage="failed", status="failed", error=str(exc))
            await _record_audit_run_event(audit_run_id, "pipeline_failed", {"error": str(exc), "steps": [_compact_event_payload(step) for step in steps]})
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

    @router.get("/audit-runs/{audit_run_id}/events")
    async def audit_run_events(audit_run_id: str) -> list[dict[str, Any]]:
        return await _list_audit_run_events(audit_run_id)

    @router.get("/audit-runs/{audit_run_id}/pipeline-status")
    async def audit_run_pipeline_status(audit_run_id: str) -> dict[str, Any]:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        findings = await _list_findings(audit_run_id)
        attempts = await _list_validation_attempts(audit_run_id)
        reports = await _list_reports(audit_run_id)
        events = await _list_audit_run_events(audit_run_id, limit=100)
        attempt_counts: dict[str, int] = {}
        for attempt in attempts:
            status = str(attempt.get("status") or "unknown")
            attempt_counts[status] = attempt_counts.get(status, 0) + 1
        finding_counts: dict[str, int] = {}
        for finding in findings:
            status = str(finding.get("status") or "unknown")
            finding_counts[status] = finding_counts.get(status, 0) + 1
        return {
            "audit_run": audit_run,
            "pipeline": (audit_run.get("config") or {}).get("pipeline", {}),
            "current": (audit_run.get("config") or {}).get("pipeline_state", {}),
            "runtime_control": (audit_run.get("config") or {}).get("runtime_control", {}),
            "counts": {
                "findings": finding_counts,
                "validation_attempts": attempt_counts,
                "reports": len(reports),
            },
            "events": events,
        }

    @router.get("/audit-runs/{audit_run_id}/validation-attempts")
    async def audit_run_validation_attempts(audit_run_id: str) -> list[dict[str, Any]]:
        return await _list_validation_attempts(audit_run_id)

    @router.get("/audit-runs/{audit_run_id}/reports")
    async def audit_run_reports(audit_run_id: str) -> list[dict[str, Any]]:
        return await _list_reports(audit_run_id)

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
        detail = await _get_finding_detail(finding_id)
        if not detail:
            raise HTTPException(status_code=404, detail="finding not found")
        return detail

    @router.post("/findings/{finding_id}/poc")
    async def run_finding_poc(finding_id: str, body: RunPocRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(
                f"/findings/{finding_id}/poc",
                method="POST",
                json=body.model_dump(),
            )
        async with SessionLocal() as session:
            finding = await session.scalar(select(Finding).where(Finding.finding_id == finding_id))
            if not finding:
                raise HTTPException(status_code=404, detail="finding not found")
            audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == finding.audit_run_id))
            if not audit_run:
                raise HTTPException(status_code=404, detail="audit run not found")
            audit_run_id = finding.audit_run_id
            project_id = finding.project_id
            existing_attempts = (
                await session.execute(
                    select(ValidationAttempt).where(ValidationAttempt.finding_id == finding_id).order_by(ValidationAttempt.round_index.desc())
                )
            ).scalars()
            highest_round = max((attempt.round_index for attempt in existing_attempts), default=0)
            attempt = ValidationAttempt(
                attempt_id=str(uuid.uuid4()),
                finding_id=finding_id,
                audit_run_id=finding.audit_run_id,
                round_index=highest_round + 1,
                status="running",
                result={
                    "kind": "poc",
                    "request": body.model_dump(),
                },
            )
            session.add(attempt)
            await session.commit()

        audit_run_dict = await _get_audit_run(audit_run_id)
        workspace_path = (audit_run_dict or {}).get("config", {}).get("workspace_host_path")
        try:
            poc_result = await runtime.run_poc_container(
                audit_run_id=audit_run_id,
                project_id=project_id,
                image=body.image,
                command=body.command,
                env=body.env,
                workspace_host_path=workspace_path,
                allow_external_network=body.allow_external_network,
                retain_runtime_on_failure=body.retain_runtime_on_failure,
                timeout_seconds=body.timeout_seconds,
                mount_workspace=body.mount_workspace,
                network_name=body.network_name,
                target_url=body.target_url,
                allow_weak_isolation=body.allow_weak_isolation,
            )
            exit_code = _optional_int(poc_result.get("container", {}).get("exit_code"))
            expected_exit_code = _optional_int(body.expected_exit_code)
            matched = bool(exit_code is not None and expected_exit_code is not None and exit_code == expected_exit_code)
            status = "completed" if matched else "failed"
            summary = f"PoC exited with {exit_code}; expected {expected_exit_code}."
            async with SessionLocal() as session:
                row = await session.scalar(select(ValidationAttempt).where(ValidationAttempt.attempt_id == attempt.attempt_id))
                if row:
                    row.status = status
                    row.result = {
                        "kind": "poc",
                        "matched_expected_exit_code": matched,
                        "expected_exit_code": expected_exit_code,
                        "poc": poc_result,
                    }
                refreshed_finding = await session.scalar(select(Finding).where(Finding.finding_id == finding_id))
                if refreshed_finding and body.mark_confirmed_on_success and matched:
                    refreshed_finding.status = "confirmed"
                session.add(
                    Evidence(
                        evidence_id=str(uuid.uuid4()),
                        finding_id=finding_id,
                        audit_run_id=audit_run_id,
                        kind="poc-run",
                        summary=summary,
                        artifact_path=poc_result.get("container", {}).get("log_artifact"),
                        payload={
                            "matched_expected_exit_code": matched,
                            "expected_exit_code": expected_exit_code,
                            "poc": poc_result,
                        },
                    )
                )
                await session.commit()
            await _record_audit_run_event(
                audit_run_id,
                "finding_poc_completed",
                {"finding_id": finding_id, "attempt_id": attempt.attempt_id, "matched_expected_exit_code": matched, "poc": poc_result},
            )
            return {
                "finding_id": finding_id,
                "attempt_id": attempt.attempt_id,
                "status": status,
                "matched_expected_exit_code": matched,
                "poc": poc_result,
                "finding": await _get_finding_detail(finding_id),
            }
        except Exception as exc:
            async with SessionLocal() as session:
                row = await session.scalar(select(ValidationAttempt).where(ValidationAttempt.attempt_id == attempt.attempt_id))
                if row:
                    row.status = "failed"
                    row.result = {"kind": "poc", "error": str(exc), "request": body.model_dump()}
                session.add(
                    Evidence(
                        evidence_id=str(uuid.uuid4()),
                        finding_id=finding_id,
                        audit_run_id=audit_run_id,
                        kind="poc-error",
                        summary=f"PoC execution failed: {exc}",
                        payload={"error": str(exc), "request": body.model_dump()},
                    )
                )
                await session.commit()
            await _record_audit_run_event(audit_run_id, "finding_poc_failed", {"finding_id": finding_id, "attempt_id": attempt.attempt_id, "error": str(exc)})
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    @router.get("/platform/audit-events")
    async def list_platform_audit_events(
        limit: int = Query(default=200, ge=1, le=1000),
        service: str | None = None,
        auth_result: str | None = None,
        status_code: int | None = None,
    ) -> list[dict[str, Any]]:
        query = select(PlatformAuditEvent).order_by(PlatformAuditEvent.created_at.desc()).limit(limit)
        if service:
            query = query.where(PlatformAuditEvent.service == service)
        if auth_result:
            query = query.where(PlatformAuditEvent.auth_result == auth_result)
        if status_code:
            query = query.where(PlatformAuditEvent.status_code == status_code)
        async with SessionLocal() as session:
            rows = (await session.execute(query)).scalars()
            return [_platform_audit_event_to_dict(row) for row in rows]

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

    @router.get("/runtime/sandbox/capabilities")
    async def sandbox_capabilities() -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway("/runtime/sandbox/capabilities")
        return await runtime.sandbox_capabilities()

    @router.get("/runtime/managed")
    async def managed_runtime() -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway("/runtime/managed")
        return await runtime.managed_runtime()

    @router.post("/runtime/cleanup-expired")
    async def cleanup_expired_runtime() -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway("/runtime/cleanup-expired", method="POST")
        return await runtime.cleanup_expired_runtime()

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
        try:
            logs = await runtime.logs(audit_run_id, container_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"container logs not found: {exc}") from exc
        return Response(logs, media_type="text/plain")

    @router.post("/audit-runs/{audit_run_id}/cleanup")
    async def cleanup_audit_run(audit_run_id: str) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/cleanup", method="POST")
        return await runtime.cleanup_run(audit_run_id)

    @router.post("/audit-runs/{audit_run_id}/sandbox/poc")
    async def run_poc(audit_run_id: str, body: RunPocRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(
                f"/audit-runs/{audit_run_id}/sandbox/poc",
                method="POST",
                json=body.model_dump(),
            )
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        try:
            result = await runtime.run_poc_container(
                audit_run_id=audit_run_id,
                project_id=audit_run["project_id"],
                image=body.image,
                command=body.command,
                env=body.env,
                workspace_host_path=workspace_path,
                allow_external_network=body.allow_external_network,
                retain_runtime_on_failure=body.retain_runtime_on_failure,
                timeout_seconds=body.timeout_seconds,
                mount_workspace=body.mount_workspace,
                network_name=body.network_name,
                target_url=body.target_url,
                allow_weak_isolation=body.allow_weak_isolation,
            )
        except (DockerApiError, RuntimeError, ValueError) as exc:
            await _record_audit_run_event(audit_run_id, "poc_run_failed", {"error": str(exc), "request": body.model_dump()})
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _record_audit_run_event(audit_run_id, "poc_run_completed", result)
        return result

    @router.post("/audit-runs/{audit_run_id}/sandbox/service")
    async def start_sandbox_service(audit_run_id: str, body: StartSandboxServiceRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(
                f"/audit-runs/{audit_run_id}/sandbox/service",
                method="POST",
                json=body.model_dump(),
            )
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        try:
            result = await runtime.start_sandbox_service(
                audit_run_id=audit_run_id,
                project_id=audit_run["project_id"],
                image=body.image,
                command=body.command,
                env=body.env,
                workspace_host_path=workspace_path,
                service_name=body.service_name,
                port=body.port,
                allow_external_network=body.allow_external_network,
                retain_runtime_on_failure=body.retain_runtime_on_failure,
                startup_timeout_seconds=body.startup_timeout_seconds,
                mount_workspace=body.mount_workspace,
                healthcheck_path=body.healthcheck_path,
                allow_weak_isolation=body.allow_weak_isolation,
            )
        except (DockerApiError, RuntimeError, ValueError) as exc:
            await _record_audit_run_event(audit_run_id, "sandbox_service_failed", {"error": str(exc), "request": body.model_dump()})
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _record_audit_run_event(audit_run_id, "sandbox_service_started", result)
        return result

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


def _platform_audit_event_to_dict(row: PlatformAuditEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "service": row.service,
        "method": row.method,
        "path": row.path,
        "status_code": row.status_code,
        "client_host": row.client_host,
        "user_agent": row.user_agent,
        "auth_enabled": row.auth_enabled,
        "auth_result": row.auth_result,
        "request_id": row.request_id,
        "metadata": row.metadata_json,
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


async def _get_finding_detail(finding_id: str) -> dict[str, Any] | None:
    async with SessionLocal() as session:
        finding = await session.scalar(select(Finding).where(Finding.finding_id == finding_id))
        if not finding:
            return None
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


async def _request_pipeline_cancel(audit_run_id: str, *, reason: str) -> None:
    async with SessionLocal() as session:
        audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
        if not audit_run:
            return
        config = dict(audit_run.config or {})
        control = dict(config.get("runtime_control") or {})
        control.update(
            {
                "cancel_requested": True,
                "cancel_reason": reason,
                "cancel_requested_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        config["runtime_control"] = control
        audit_run.config = config
        await session.commit()


async def _clear_pipeline_cancel(audit_run_id: str) -> None:
    async with SessionLocal() as session:
        audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
        if not audit_run:
            return
        config = dict(audit_run.config or {})
        control = dict(config.get("runtime_control") or {})
        if control:
            control["cancel_requested"] = False
            control.pop("cancel_reason", None)
            control.pop("cancel_requested_at", None)
            config["runtime_control"] = control
            audit_run.config = config
            await session.commit()


async def _is_cancel_requested(audit_run_id: str) -> bool:
    audit_run = await _get_audit_run(audit_run_id)
    control = ((audit_run or {}).get("config") or {}).get("runtime_control") or {}
    return bool(control.get("cancel_requested"))


async def _cancel_reason(audit_run_id: str) -> str | None:
    audit_run = await _get_audit_run(audit_run_id)
    control = ((audit_run or {}).get("config") or {}).get("runtime_control") or {}
    reason = control.get("cancel_reason")
    return str(reason) if reason else None


async def _raise_if_cancelled(audit_run_id: str) -> None:
    if await _is_cancel_requested(audit_run_id):
        raise PipelineCancelled(await _cancel_reason(audit_run_id) or "cancel_requested")


def _is_active_audit_status(status: str | None) -> bool:
    return status in {"queued", "running", "validating", "cancelling"}


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


async def _list_reports(audit_run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(ReportArtifact)
                .where(ReportArtifact.audit_run_id == audit_run_id)
                .order_by(ReportArtifact.created_at.desc())
            )
        ).scalars()
        return [_report_to_dict(row) for row in rows]


async def _list_audit_run_events(audit_run_id: str, limit: int = 200) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(AuditRunEvent)
                .where(AuditRunEvent.audit_run_id == audit_run_id)
                .order_by(AuditRunEvent.created_at.desc())
                .limit(limit)
            )
        ).scalars()
        return [
            {
                "id": row.id,
                "audit_run_id": row.audit_run_id,
                "event_type": row.event_type,
                "payload": row.payload,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


async def _list_agent_runs(audit_run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(AgentRun).where(AgentRun.audit_run_id == audit_run_id).order_by(AgentRun.created_at.asc()))
        ).scalars()
        return [_agent_run_to_dict(row) for row in rows]


async def _record_pipeline_event(audit_run_id: str, event_type: str, payload: dict[str, Any]) -> None:
    await _record_audit_run_event(audit_run_id, event_type, payload)
    async with SessionLocal() as session:
        agent_run = await session.scalar(
            select(AgentRun).where(AgentRun.audit_run_id == audit_run_id).order_by(AgentRun.created_at.desc())
        )
        if agent_run:
            session.add(AgentRunEvent(agent_run_id=agent_run.agent_run_id, event_type=event_type, payload=payload))
            await session.commit()


async def _record_audit_run_event(audit_run_id: str, event_type: str, payload: dict[str, Any]) -> None:
    async with SessionLocal() as session:
        session.add(
            AuditRunEvent(
                audit_run_id=audit_run_id,
                event_type=event_type,
                payload=_compact_event_payload(payload),
            )
        )
        await session.commit()


async def _set_pipeline_state(
    audit_run_id: str,
    *,
    stage: str,
    status: str,
    error: str | None = None,
) -> None:
    async with SessionLocal() as session:
        audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
        if not audit_run:
            return
        config = dict(audit_run.config or {})
        state = {
            "stage": stage,
            "status": status,
        }
        if error:
            state["error"] = error
        config["pipeline_state"] = state
        audit_run.config = config
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


def _compact_event_payload(value: Any, *, max_string: int = 1200, max_items: int = 20, depth: int = 0) -> Any:
    if depth > 4:
        return "<truncated-depth>"
    if isinstance(value, str):
        return value if len(value) <= max_string else f"{value[:max_string]}...<truncated {len(value) - max_string} chars>"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        compacted = [_compact_event_payload(item, max_string=max_string, max_items=max_items, depth=depth + 1) for item in value[:max_items]]
        if len(value) > max_items:
            compacted.append(f"<truncated {len(value) - max_items} items>")
        return compacted
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                result["<truncated>"] = f"{len(value) - max_items} keys"
                break
            result[str(key)] = _compact_event_payload(item, max_string=max_string, max_items=max_items, depth=depth + 1)
        return result
    return repr(value)


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

import asyncio
import contextlib
import json
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, BackgroundTasks, Body, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete, func, select

from app.api.readiness import (
    active_pipeline_readiness_check as _active_pipeline_readiness_check,
    embedding_readiness_remediation as _embedding_readiness_remediation,
    http_guardrails_readiness_check as _http_guardrails_readiness_check,
    normalized_pipeline_backend as _normalized_pipeline_backend,
    pipeline_backend_readiness_check as _pipeline_backend_readiness_check,
    sandbox_readiness_remediation as _sandbox_readiness_remediation,
    summarize_readiness_checks as _summarize_readiness_checks,
    template_readiness_checks as _template_readiness_checks,
    vector_store_readiness_remediation as _vector_store_readiness_remediation,
    workspace_import_readiness_check as _workspace_import_readiness_check,
)
from app.api.serializers import (
    agent_runtime_to_dict as _agent_runtime_to_dict,
    agent_run_to_dict as _agent_run_to_dict,
    agent_transcript_event_to_dict as _agent_transcript_event_to_dict,
    artifact_metadata_or_none as _artifact_metadata_or_none,
    attempt_to_dict as _attempt_to_dict,
    audit_run_to_dict as _audit_run_to_dict,
    code_analysis_task_to_dict as _code_analysis_task_to_dict,
    deliverable_artifact_to_dict as _deliverable_artifact_to_dict,
    dependency_record_to_dict as _dependency_record_to_dict,
    evidence_to_dict as _evidence_to_dict,
    finding_triage_decision_to_dict as _finding_triage_decision_to_dict,
    finding_markdown_reference as _finding_markdown_reference,
    finding_to_dict as _finding_to_dict,
    knowledge_chunk_from_row as _knowledge_chunk_from_row,
    knowledge_chunk_to_dict as _knowledge_chunk_to_dict,
    knowledge_document_to_dict as _knowledge_document_to_dict,
    platform_audit_event_to_dict as _platform_audit_event_to_dict,
    project_to_dict as _project_to_dict,
    report_to_dict as _report_to_dict,
    snapshot_to_dict as _snapshot_to_dict,
    whiteboard_card_to_dict as _whiteboard_card_to_dict,
    whiteboard_edge_to_dict as _whiteboard_edge_to_dict,
    whiteboard_task_to_dict as _whiteboard_task_to_dict,
)
from app.domain.models import (
    AgentRuntime,
    AgentRun,
    AgentRunEvent,
    AgentTranscriptEvent,
    ArtifactRecord,
    ApiKeyRecord,
    AuditRun,
    AuditRunEvent,
    CodeAnalysisTask,
    ContainerRun,
    DeliverableArtifact,
    DependencyRecord,
    Evidence,
    Finding,
    FindingTriageDecision,
    KnowledgeChunk,
    KnowledgeDocument,
    PlatformAuditEvent,
    Project,
    ProjectSnapshot,
    ReportArtifact,
    ValidationAttempt,
    WhiteboardTask,
    WhiteboardCard,
    WhiteboardEdge,
    WorkerHeartbeat,
)
from app.integrations.docker import DockerApiError
from app.integrations.protocols import classify_agent_protocol, fetch_a2a_agent_card, serialize_capabilities
from app.repositories import SessionLocal
from app.schemas import (
    A2AAgentCardRequest,
    AgentTranscriptEventsRequest,
    CodeBatchAnalysisRequest,
    CreateAuditRunRequest,
    CreateApiKeyRequest,
    CreateFindingRequest,
    CreateProjectRequest,
    CreateWhiteboardCardRequest,
    CreateWhiteboardEdgeRequest,
    CreateWhiteboardNoteRequest,
    CreateWhiteboardScheduleRequest,
    CreateWhiteboardSubscriptionRequest,
    DecideWhiteboardScheduleRequest,
    EnsureAgentRuntimeRequest,
    KnowledgeSearchRequest,
    RunPocRequest,
    RunWhiteboardTasksRequest,
    SearchWhiteboardCardsRequest,
    StartSandboxComposeRequest,
    StartAgentRunRequest,
    StartSandboxServiceRequest,
    StorageCleanupRequest,
    SubmitWhiteboardEvidenceRequest,
    TemplateBody,
    UpdateWhiteboardCardRequest,
    UpdateWhiteboardNotificationRequest,
    ValidatorScaleRequest,
)
from app.services.artifacts import (
    ArtifactAccessError,
    ArtifactStore,
    artifact_absolute_path,
    artifact_path_matches,
    artifact_storage_backend,
    relative_path_for_artifact_id,
    resolve_artifact_path,
    secure_artifact_headers,
)
from app.services.auth import (
    api_key_record_to_dict,
    auth_is_enabled,
    create_persisted_api_key,
    get_current_api_key,
    has_scope,
    normalize_scopes,
)
from app.services.code_analysis import CodeAuditPlanner
from app.services.decompiler import DecompilerService
from app.services.dependency_scanner import DependencyScanner
from app.services.finding_dedupe import find_existing_finding, finding_identity
from app.services.knowledge import KnowledgeIndexError, KnowledgeService
from app.services.pipeline_executor import PipelineCancelled, PipelineExecutor
from app.services.pipeline_recovery import is_active_pipeline
from app.services.storage_cleanup import StorageCleanupService
from app.services.templates import TemplateStore
from app.services.whiteboard import WhiteboardService
from app.services.worker_heartbeat import list_worker_heartbeats, workflow_worker_health
from app.services.workspace import WorkspaceImportError, WorkspaceService
from app.settings import Settings, get_settings


router = APIRouter()


def register_runtime_routes(settings: Settings, runtime_provider: callable) -> APIRouter:
    def agent_template_store() -> TemplateStore:
        return TemplateStore(settings.config_root, "agent-templates", include_demo=settings.enable_demo_templates)

    def mcp_template_store() -> TemplateStore:
        return TemplateStore(settings.config_root, "mcp-templates", include_demo=settings.enable_demo_templates)

    async def proxy_gateway(path: str, *, method: str = "GET", json: dict[str, Any] | None = None) -> Any:
        headers = {}
        api_key = get_current_api_key() or settings.dieaudit_api_key
        if api_key:
            headers[settings.api_key_header] = api_key
        async with httpx.AsyncClient(base_url=settings.agent_gateway_url, timeout=120) as client:
            response = await client.request(method, path, json=json, headers=headers)
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    def pipeline_executor(runtime: Any) -> PipelineExecutor:
        return PipelineExecutor(
            settings=settings,
            runtime=runtime,
            get_audit_run=_get_audit_run,
            mark_audit_run_status=_mark_audit_run_status,
            set_pipeline_state=_set_pipeline_state,
            record_audit_run_event=_record_audit_run_event,
            record_pipeline_event=_record_pipeline_event,
            record_pipeline_summary=_record_pipeline_summary,
            raise_if_cancelled=_raise_if_cancelled,
            is_cancel_requested=_is_cancel_requested,
            cancel_reason=_cancel_reason,
            list_findings=_list_findings,
            run_structure_discovery=_run_structure_discovery,
            run_code_batch_analysis=_run_code_batch_analysis,
            run_source_sink_analysis=_run_source_sink_analysis,
            run_source_sink_finding=_run_source_sink_finding_internal,
            complete_source_sink_analysis=_complete_source_sink_analysis_internal,
            run_whiteboard_swarm=_run_whiteboard_swarm,
            run_judger_finding=_run_judger_finding_internal,
            complete_judgement=_complete_judgement_internal,
            run_poc_writer_finding=_run_poc_writer_finding_internal,
            complete_poc_writing=_complete_poc_writing_internal,
            run_poc_verifier_finding=_run_poc_verifier_finding_internal,
            complete_poc_verification=_complete_poc_verification_internal,
            list_evidence=_list_evidence,
            run_sca=_run_sca_mcp,
            run_semgrep=_run_semgrep_mcp,
            judge_audit_run=_judge_audit_run_internal,
            generate_pocs=_generate_pocs_internal,
            verify_pocs=_verify_pocs_internal,
            generate_report=_generate_report_internal,
            compact_event_payload=_compact_event_payload,
        )

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
        body = (
            f'dieaudit_service_up{{service="{settings.service_name}"}} 1\n'
            f'dieaudit_artifact_storage_backend{{backend="{artifact_storage_backend(settings)}"}} 1\n'
            f"dieaudit_demo_templates_enabled {1 if settings.enable_demo_templates else 0}\n"
            f"dieaudit_weak_runc_sandbox_enabled {1 if settings.allow_runc_sandbox else 0}\n"
        )
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

    @router.get("/auth/me")
    async def current_auth_principal(request: Request) -> dict[str, Any]:
        principal = getattr(request.state, "auth_principal", None)
        return {"authenticated": bool(principal), "principal": principal}

    @router.get("/auth/api-keys")
    async def list_api_keys(request: Request) -> list[dict[str, Any]]:
        await _require_admin(request, settings)
        async with SessionLocal() as session:
            rows = (await session.execute(select(ApiKeyRecord).order_by(ApiKeyRecord.created_at.desc()))).scalars()
            return [api_key_record_to_dict(row) for row in rows]

    @router.post("/auth/api-keys")
    async def create_api_key(request: Request, body: CreateApiKeyRequest) -> dict[str, Any]:
        await _require_admin(request, settings)
        return await create_persisted_api_key(
            name=body.name,
            scopes=body.scopes,
            metadata=body.metadata,
            default_scope="read",
        )

    @router.post("/auth/api-keys/{key_id}/deactivate")
    async def deactivate_api_key(request: Request, key_id: str) -> dict[str, Any]:
        await _require_admin(request, settings)
        async with SessionLocal() as session:
            row = await session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.key_id == key_id))
            if not row:
                raise HTTPException(status_code=404, detail="api key not found")
            row.status = "inactive"
            row.deactivated_at = datetime.now(timezone.utc)
            await session.flush()
            await session.refresh(row)
            record = api_key_record_to_dict(row)
            await session.commit()
            return record

    @router.get("/knowledge/documents")
    async def list_knowledge_documents(
        request: Request,
        scope: str | None = Query(default=None),
        project_id: str | None = Query(default=None),
    ) -> list[dict[str, Any]]:
        principal = getattr(request.state, "auth_principal", None)
        if project_id:
            await _require_project_access(principal, project_id)
        async with SessionLocal() as session:
            query = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
            if scope:
                query = query.where(KnowledgeDocument.scope == scope)
            if project_id:
                query = query.where(KnowledgeDocument.project_id == project_id)
            rows = (await session.execute(query)).scalars()
            rows_list = list(rows)
        allowed = []
        for row in rows_list:
            if row.project_id and not await _principal_can_access_project(principal, row.project_id):
                continue
            allowed.append(row)
        return [_knowledge_document_to_dict(row) for row in allowed]

    @router.get("/knowledge/status")
    async def knowledge_status() -> dict[str, Any]:
        service = KnowledgeService(settings)
        async with SessionLocal() as session:
            document_count = await _count_rows(session, KnowledgeDocument)
            chunk_count = await _count_rows(session, KnowledgeChunk)
        return {
            "embedding": await service.embedding_health(probe=settings.knowledge_embedding_probe_on_readiness),
            "vector_store": await service.collection_health(probe=settings.knowledge_embedding_probe_on_readiness),
            "documents": {
                "document_count": document_count,
                "chunk_count": chunk_count,
            },
        }

    @router.post("/knowledge/documents")
    async def upload_knowledge_document(
        request: Request,
        title: str = Form(...),
        scope: str = Form("global"),
        project_id: str | None = Form(None),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        normalized_scope = _normalize_knowledge_scope(scope)
        if normalized_scope == "project" and not project_id:
            raise HTTPException(status_code=400, detail="project_id is required for project-scoped knowledge")
        if normalized_scope == "project" and project_id:
            await _require_project_access(getattr(request.state, "auth_principal", None), project_id)
        elif _principal_has_resource_limits(getattr(request.state, "auth_principal", None)):
            raise HTTPException(status_code=403, detail="global knowledge upload requires unrestricted API key scope")
        document_id = str(uuid.uuid4())
        service = KnowledgeService(settings)
        artifact_path = service.save_upload(
            document_id=document_id,
            filename=file.filename or "knowledge-document.txt",
            stream=file.file,
        )
        try:
            text = service.extract_text(artifact_path, file.content_type)
            chunk_rows = service.chunk_rows(
                document_id=document_id,
                title=title,
                source_name=file.filename or artifact_path.name,
                scope=normalized_scope,
                project_id=project_id,
                text=text,
            )
            if not chunk_rows:
                raise KnowledgeIndexError("document did not contain indexable text")
            await service.upsert_chunks(chunk_rows)
            status = "indexed"
            error = None
        except Exception as exc:
            chunk_rows = []
            status = "failed"
            error = str(exc)
        document = KnowledgeDocument(
            document_id=document_id,
            title=title,
            source_name=file.filename or artifact_path.name,
            content_type=file.content_type,
            scope=normalized_scope,
            project_id=project_id if normalized_scope == "project" else None,
            status=status,
            chunk_count=len(chunk_rows),
            artifact_path=str(artifact_path),
            metadata_json={"error": error} if error else {},
        )
        async with SessionLocal() as session:
            session.add(document)
            for row in chunk_rows:
                session.add(
                    KnowledgeChunk(
                        chunk_id=row["chunk_id"],
                        document_id=row["document_id"],
                        scope=row["scope"],
                        project_id=row["project_id"],
                        chunk_index=row["chunk_index"],
                        text=row["text"],
                        token_count=row["token_count"],
                        vector_id=row["vector_id"],
                        metadata_json={
                            "title": row["title"],
                            "source_name": row["source_name"],
                        },
                    )
                )
            await session.commit()
            return {"document": _knowledge_document_to_dict(document), "chunks_indexed": len(chunk_rows)}

    @router.get("/knowledge/documents/{document_id}")
    async def get_knowledge_document(request: Request, document_id: str) -> dict[str, Any]:
        async with SessionLocal() as session:
            row = await session.scalar(select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id))
            if not row:
                raise HTTPException(status_code=404, detail="knowledge document not found")
            if row.project_id:
                await _require_project_access(getattr(request.state, "auth_principal", None), row.project_id)
            elif _principal_has_resource_limits(getattr(request.state, "auth_principal", None)):
                raise HTTPException(status_code=403, detail="global knowledge document is outside API key project or audit run scope")
            return _knowledge_document_to_dict(row)

    @router.post("/knowledge/documents/{document_id}/reindex")
    async def reindex_knowledge_document(request: Request, document_id: str) -> dict[str, Any]:
        service = KnowledgeService(settings)
        async with SessionLocal() as session:
            document = await session.scalar(select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id))
            if not document:
                raise HTTPException(status_code=404, detail="knowledge document not found")
            if document.project_id:
                await _require_project_access(getattr(request.state, "auth_principal", None), document.project_id)
            elif _principal_has_resource_limits(getattr(request.state, "auth_principal", None)):
                raise HTTPException(status_code=403, detail="global knowledge document is outside API key project or audit run scope")
            artifact_path = Path(document.artifact_path or "")
            if not artifact_path.is_file():
                with contextlib.suppress(KnowledgeIndexError):
                    await service.delete_document_vectors(document_id)
                document.status = "failed"
                document.chunk_count = 0
                document.metadata_json = {"error": f"artifact not found: {document.artifact_path}"}
                await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
                await session.commit()
                raise HTTPException(status_code=409, detail=document.metadata_json["error"])
            try:
                text = service.extract_text(artifact_path, document.content_type)
                chunk_rows = service.chunk_rows(
                    document_id=document_id,
                    title=document.title,
                    source_name=document.source_name,
                    scope=document.scope,
                    project_id=document.project_id,
                    text=text,
                )
                if not chunk_rows:
                    raise KnowledgeIndexError("document did not contain indexable text")
                await service.delete_document_vectors(document_id)
                await service.upsert_chunks(chunk_rows)
            except Exception as exc:
                with contextlib.suppress(KnowledgeIndexError):
                    await service.delete_document_vectors(document_id)
                document.status = "failed"
                document.chunk_count = 0
                document.metadata_json = {"error": str(exc)}
                await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
                await session.commit()
                return {"document": _knowledge_document_to_dict(document), "chunks_indexed": 0, "error": str(exc)}
            await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
            for row in chunk_rows:
                session.add(_knowledge_chunk_from_row(row))
            document.status = "indexed"
            document.chunk_count = len(chunk_rows)
            document.metadata_json = {}
            await session.commit()
            return {"document": _knowledge_document_to_dict(document), "chunks_indexed": len(chunk_rows)}

    @router.delete("/knowledge/documents/{document_id}")
    async def delete_knowledge_document(request: Request, document_id: str) -> dict[str, Any]:
        service = KnowledgeService(settings)
        async with SessionLocal() as session:
            document = await session.scalar(select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id))
            if not document:
                raise HTTPException(status_code=404, detail="knowledge document not found")
            if document.project_id:
                await _require_project_access(getattr(request.state, "auth_principal", None), document.project_id)
            elif _principal_has_resource_limits(getattr(request.state, "auth_principal", None)):
                raise HTTPException(status_code=403, detail="global knowledge document is outside API key project or audit run scope")
            artifact_path = Path(document.artifact_path).resolve() if document.artifact_path else None
            try:
                await service.delete_document_vectors(document_id)
            except KnowledgeIndexError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
            await session.delete(document)
            await session.commit()
        deleted_artifact = False
        if artifact_path:
            deleted_artifact = _delete_knowledge_artifact(settings, artifact_path)
        return {"document_id": document_id, "deleted": True, "artifact_deleted": deleted_artifact}

    @router.get("/knowledge/documents/{document_id}/chunks")
    async def list_knowledge_chunks(request: Request, document_id: str) -> list[dict[str, Any]]:
        async with SessionLocal() as session:
            document = await session.scalar(select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id))
            if not document:
                raise HTTPException(status_code=404, detail="knowledge document not found")
            if document.project_id:
                await _require_project_access(getattr(request.state, "auth_principal", None), document.project_id)
            elif _principal_has_resource_limits(getattr(request.state, "auth_principal", None)):
                raise HTTPException(status_code=403, detail="global knowledge document is outside API key project or audit run scope")
            rows = (
                await session.execute(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.document_id == document_id)
                    .order_by(KnowledgeChunk.chunk_index.asc())
                )
            ).scalars()
            return [_knowledge_chunk_to_dict(row) for row in rows]

    @router.post("/knowledge/search")
    async def search_knowledge(request: Request, body: KnowledgeSearchRequest) -> dict[str, Any]:
        principal = getattr(request.state, "auth_principal", None)
        if body.project_id:
            await _require_project_access(principal, body.project_id)
        elif _principal_has_resource_limits(principal) and body.include_global:
            raise HTTPException(status_code=403, detail="global knowledge search requires unrestricted API key scope")
        service = KnowledgeService(settings)
        try:
            matches = await service.search(
                query=body.query,
                project_id=body.project_id,
                include_global=body.include_global,
                limit=body.limit,
            )
        except KnowledgeIndexError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        chunk_ids = [item["chunk_id"] for item in matches if item.get("chunk_id")]
        chunks_by_id: dict[str, KnowledgeChunk] = {}
        if chunk_ids:
            async with SessionLocal() as session:
                rows = (await session.execute(select(KnowledgeChunk).where(KnowledgeChunk.chunk_id.in_(chunk_ids)))).scalars()
                chunks_by_id = {row.chunk_id: row for row in rows}
        enriched = []
        for item in matches:
            chunk = chunks_by_id.get(str(item.get("chunk_id")))
            if not chunk:
                continue
            enriched.append(
                {
                    **item,
                    "text": chunk.text,
                    "metadata": chunk.metadata_json or {},
                    "evidence": _knowledge_evidence_from_match(item, chunk),
                }
            )
        return {"query": body.query, "matches": enriched}

    @router.get("/projects")
    async def list_projects(request: Request) -> list[dict[str, Any]]:
        principal = getattr(request.state, "auth_principal", None)
        async with SessionLocal() as session:
            rows = (await session.execute(select(Project).order_by(Project.created_at.desc()))).scalars()
            project_rows = list(rows)
        allowed = [row for row in project_rows if await _principal_can_access_project(principal, row.project_id)]
        return [_project_to_dict(row) for row in allowed]

    @router.post("/projects")
    async def create_project(request: Request, body: CreateProjectRequest) -> dict[str, Any]:
        _require_unrestricted_resource_scope(getattr(request.state, "auth_principal", None), "project creation")
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
        request: Request,
        name: str = Form(...),
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        _require_unrestricted_resource_scope(getattr(request.state, "auth_principal", None), "project creation")
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
    async def get_project(request: Request, project_id: str) -> dict[str, Any]:
        project = await _get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="project not found")
        await _require_project_access(getattr(request.state, "auth_principal", None), project_id)
        return project

    @router.get("/projects/{project_id}/snapshots")
    async def list_project_snapshots(request: Request, project_id: str) -> list[dict[str, Any]]:
        await _require_project_access(getattr(request.state, "auth_principal", None), project_id)
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
    async def create_audit_run(request: Request, project_id: str, body: CreateAuditRunRequest) -> dict[str, Any]:
        principal = getattr(request.state, "auth_principal", None)
        await _require_project_access(principal, project_id)
        if _principal_allowed_audit_run_ids(principal):
            raise HTTPException(status_code=403, detail="audit run creation requires project-only or unrestricted API key scope")
        async with SessionLocal() as session:
            project = await session.scalar(select(Project).where(Project.project_id == project_id))
            if not project:
                raise HTTPException(status_code=404, detail="project not found")
            snapshot = await _resolve_snapshot(session, project_id, body.snapshot_id)
            audit_run_id = str(uuid.uuid4())
            input_payload = dict(body.input_payload or {})
            if body.preflight_prompt:
                input_payload["preflight_prompt"] = body.preflight_prompt
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
                    "enabled_agents": body.enabled_agents,
                    "preflight_prompt": body.preflight_prompt,
                    "input_payload": input_payload,
                    "workspace_host_path": snapshot.workspace_path,
                    "enable_code_batch_analysis": body.enable_code_batch_analysis,
                    "enable_batch_internal_semgrep": body.enable_batch_internal_semgrep,
                    "enable_batch_internal_sca": body.enable_batch_internal_sca,
                    "max_code_audit_tasks": body.max_code_audit_tasks,
                    "max_files_per_code_audit_task": body.max_files_per_code_audit_task,
                    "max_parallel_code_auditors": body.max_parallel_code_auditors,
                    "code_auditor_agent_name": body.code_auditor_agent_name,
                    "enable_source_sink_analysis": body.enable_source_sink_analysis,
                    "source_sink_finder_agent_name": body.source_sink_finder_agent_name,
                    "max_parallel_source_sink_finders": body.max_parallel_source_sink_finders,
                    "max_source_sink_findings": body.max_source_sink_findings,
                    "enable_validators": body.enable_validators,
                    "validator_agent_name": body.validator_agent_name,
                    "enable_validation_judgement": body.enable_validation_judgement,
                    "validation_judgement_agent_name": body.validation_judgement_agent_name,
                    "enable_judgement": body.enable_judgement,
                    "judger_agent_name": body.judger_agent_name,
                    "max_parallel_judgers": body.max_parallel_judgers,
                    "enable_poc_writing": body.enable_poc_writing,
                    "poc_writer_agent_name": body.poc_writer_agent_name,
                    "max_parallel_poc_writers": body.max_parallel_poc_writers,
                    "max_poc_findings": body.max_poc_findings,
                    "enable_poc_verification": body.enable_poc_verification,
                    "poc_verifier_agent_name": body.poc_verifier_agent_name,
                    "max_parallel_poc_verifiers": body.max_parallel_poc_verifiers,
                    "enable_decompilation": body.enable_decompilation,
                    "decompiled_source_dir": body.decompiled_source_dir,
                    "decompile_max_artifact_size_mb": body.decompile_max_artifact_size_mb,
                    "decompile_timeout_seconds": body.decompile_timeout_seconds,
                    "decompile_max_artifacts": body.decompile_max_artifacts,
                    "enable_feedback_loop": body.enable_feedback_loop,
                    "max_feedback_rounds": body.max_feedback_rounds,
                    "enable_whiteboard": body.enable_whiteboard,
                    "enable_whiteboard_swarm": body.enable_whiteboard_swarm,
                    "whiteboard_swarm_agent_name": body.whiteboard_swarm_agent_name or body.agent_name,
                    "max_whiteboard_rounds": body.max_whiteboard_rounds,
                    "max_whiteboard_tasks_per_round": body.max_whiteboard_tasks_per_round,
                },
            )
            session.add(audit_run)
            await session.commit()
            await WhiteboardService(settings, session).write_snapshot(audit_run_id)
        agent_result = None
        if body.start_agent:
            start_body = StartAgentRunRequest(
                audit_run_id=audit_run_id,
                project_id=project_id,
                agent_name=body.agent_name,
                workspace_host_path=snapshot.workspace_path,
                allow_external_network=body.allow_external_network,
                retain_runtime_on_failure=body.retain_runtime_on_failure,
                input_payload=input_payload
                or {
                    "goal": "Run an initial code audit pass over the mounted project and report vulnerability candidates with file paths."
                },
            )
            agent_result = await _start_agent_run_impl(audit_run_id, start_body)
            await _mark_audit_run_status(audit_run_id, "agent_completed")
        return {"audit_run": await _get_audit_run(audit_run_id), "agent_run": agent_result}

    @router.get("/audit-runs/{audit_run_id}")
    async def get_audit_run(request: Request, audit_run_id: str) -> dict[str, Any]:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
        return audit_run

    @router.get("/audit-runs/{audit_run_id}/findings")
    async def list_findings(request: Request, audit_run_id: str) -> list[dict[str, Any]]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(Finding).where(Finding.audit_run_id == audit_run_id).order_by(Finding.created_at.desc())
                )
            ).scalars()
            return [_finding_to_dict(row) for row in rows]

    @router.get("/audit-runs/{audit_run_id}/whiteboard")
    async def get_whiteboard(request: Request, audit_run_id: str) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.graph(audit_run_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/whiteboard/search")
    async def search_whiteboard_cards(request: Request, audit_run_id: str, body: SearchWhiteboardCardsRequest) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.search_cards(audit_run_id, body.model_dump())
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/audit-runs/{audit_run_id}/whiteboard/events")
    async def list_whiteboard_events(
        request: Request,
        audit_run_id: str,
        limit: int = Query(default=100, ge=1, le=500),
        after_event_id: str | None = None,
    ) -> list[dict[str, Any]]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.list_events(audit_run_id, limit=limit, after_event_id=after_event_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/whiteboard/subscriptions")
    async def create_whiteboard_subscription(request: Request, audit_run_id: str, body: CreateWhiteboardSubscriptionRequest) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.subscribe(audit_run_id, body.model_dump())
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/audit-runs/{audit_run_id}/whiteboard/notifications")
    async def list_whiteboard_notifications(
        request: Request,
        audit_run_id: str,
        status: str | None = None,
        subscriber_agent_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.list_notifications(
                    audit_run_id,
                    status=status,
                    subscriber_agent_run_id=subscriber_agent_run_id,
                )
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/whiteboard/notifications/{notification_id}")
    async def update_whiteboard_notification(
        request: Request,
        audit_run_id: str,
        notification_id: str,
        body: UpdateWhiteboardNotificationRequest,
    ) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.update_notification(
                    audit_run_id,
                    notification_id,
                    body.status,
                    claimed_by_agent_run_id=body.claimed_by_agent_run_id,
                    lease_seconds=body.lease_seconds,
                )
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/whiteboard/schedule-requests")
    async def create_whiteboard_schedule_request(request: Request, audit_run_id: str, body: CreateWhiteboardScheduleRequest) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.create_schedule_request(audit_run_id, body.model_dump())
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/whiteboard/schedule-requests/{request_id}/decide")
    async def decide_whiteboard_schedule_request(
        request: Request,
        audit_run_id: str,
        request_id: str,
        body: DecideWhiteboardScheduleRequest,
    ) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                result = await service.decide_schedule_request(audit_run_id, request_id, body.model_dump())
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result.get("status") in {"approved", "scheduled"}:
            audit_run = await _get_audit_run(audit_run_id)
            runtime = runtime_provider()
            if audit_run and runtime is not None:
                config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
                workspace_path = config.get("workspace_host_path")
                agent_name = str(body.agent_name or result.get("suggested_agent_name") or "kimi-source-sink-finder")
                agent_result = await runtime.start_agent_run(
                    audit_run_id=audit_run_id,
                    project_id=audit_run["project_id"],
                    agent_name=agent_name,
                    workspace_host_path=workspace_path,
                    allow_external_network=_effective_agent_external_network(audit_run, get_settings()),
                    retain_runtime_on_failure=bool(audit_run.get("retain_runtime_on_failure")),
                    input_payload={
                        "goal": result.get("goal"),
                        "long_running": True,
                        "agent_lifecycle": "long-running",
                        "audit_phase": "whiteboard-requested-agent",
                        "whiteboard": {
                            "schedule_request_id": result.get("request_id"),
                            "task_id": result.get("task_id"),
                            "related_card_ids": result.get("related_card_ids") or [],
                            "instruction": "Read the Whiteboard, subscribe to relevant changes, and keep working until the requested goal is resolved or blocked.",
                        },
                    },
                )
                result = {**result, "agent_run": _compact_event_payload(agent_result)}
        return result

    @router.get("/audit-runs/{audit_run_id}/whiteboard/agent-graph")
    async def get_whiteboard_agent_graph(request: Request, audit_run_id: str) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.agent_graph(audit_run_id)
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/whiteboard/cards")
    async def create_whiteboard_card(request: Request, audit_run_id: str, body: CreateWhiteboardCardRequest) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.create_card(audit_run_id, body.model_dump())
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/audit-runs/{audit_run_id}/whiteboard/cards/{card_id}")
    async def update_whiteboard_card(request: Request, audit_run_id: str, card_id: str, body: UpdateWhiteboardCardRequest) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.update_card(audit_run_id, card_id, body.model_dump(exclude_unset=True))
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/whiteboard/edges")
    async def create_whiteboard_edge(request: Request, audit_run_id: str, body: CreateWhiteboardEdgeRequest) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.create_edge(audit_run_id, body.model_dump())
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/whiteboard/notes")
    async def add_whiteboard_note(request: Request, audit_run_id: str, body: CreateWhiteboardNoteRequest) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.add_note(audit_run_id, body.model_dump())
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/whiteboard/tasks/run")
    async def run_whiteboard_tasks(request: Request, audit_run_id: str, body: RunWhiteboardTasksRequest) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        try:
            return await _run_whiteboard_swarm(
                audit_run_id,
                runtime_provider(),
                override_rounds=body.rounds,
                override_max_tasks_per_round=body.max_tasks_per_round,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/whiteboard/evidence")
    async def submit_whiteboard_evidence(request: Request, audit_run_id: str, body: SubmitWhiteboardEvidenceRequest) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            service = WhiteboardService(settings, session)
            try:
                return await service.submit_chain_evidence(audit_run_id, body.model_dump())
            except LookupError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/findings")
    async def create_finding(request: Request, audit_run_id: str, body: CreateFindingRequest) -> dict[str, Any]:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
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

    @router.get("/audit-runs/{audit_run_id}/code-analysis/tasks")
    async def list_code_analysis_tasks(request: Request, audit_run_id: str) -> list[dict[str, Any]]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        return await _list_code_analysis_tasks(audit_run_id)

    @router.post("/audit-runs/{audit_run_id}/code-analysis")
    async def run_code_analysis(
        request: Request,
        audit_run_id: str,
        body: CodeBatchAnalysisRequest,
    ) -> dict[str, Any]:
        runtime = runtime_provider()
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/code-analysis", method="POST", json=body.model_dump())
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        if not workspace_path:
            raise HTTPException(status_code=400, detail="audit run has no workspace path")
        result = await _run_code_batch_analysis(
            audit_run_id,
            audit_run["project_id"],
            workspace_path,
            runtime,
            {
                **audit_run,
                "config": {
                    **(audit_run.get("config") or {}),
                    "max_code_audit_tasks": body.max_tasks,
                    "max_files_per_code_audit_task": body.max_files_per_task,
                    "max_parallel_code_auditors": body.max_parallel_agents,
                    "code_auditor_agent_name": body.agent_name,
                },
            },
        )
        return result

    @router.post("/audit-runs/{audit_run_id}/sca")
    async def run_sca(request: Request, audit_run_id: str) -> dict[str, Any]:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        if not workspace_path:
            raise HTTPException(status_code=400, detail="audit run has no workspace path")
        try:
            result = await DependencyScanner(workspace_path).scan_osv()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        created = []
        packages = result.get("packages", [])
        vulnerabilities = result.get("vulnerabilities", [])
        async with SessionLocal() as session:
            dependency_records = await _replace_dependency_records(
                session=session,
                audit_run_id=audit_run_id,
                project_id=audit_run["project_id"],
                packages=packages,
                vulnerabilities=vulnerabilities,
            )
            for item in result.get("findings", []):
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
                "packages": packages,
                "vulnerabilities": vulnerabilities,
                "dependency_records": dependency_records,
                "findings": [_finding_to_dict(row) for row in created],
            }

    @router.get("/audit-runs/{audit_run_id}/dependencies")
    async def audit_run_dependencies(request: Request, audit_run_id: str) -> dict[str, Any]:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
        rows = await _list_dependency_records(audit_run_id)
        by_ecosystem: dict[str, int] = {}
        vulnerable = 0
        for row in rows:
            ecosystem = row["ecosystem"] or "unknown"
            by_ecosystem[ecosystem] = by_ecosystem.get(ecosystem, 0) + 1
            if row["vulnerability_count"] > 0:
                vulnerable += 1
        return {
            "audit_run_id": audit_run_id,
            "packages": rows,
            "summary": {
                "total": len(rows),
                "vulnerable": vulnerable,
                "by_ecosystem": by_ecosystem,
            },
        }

    @router.post("/audit-runs/{audit_run_id}/run-pipeline")
    async def run_pipeline(request: Request, audit_run_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
        runtime = runtime_provider()
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/run-pipeline", method="POST")
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        if not workspace_path:
            raise HTTPException(status_code=400, detail="audit run has no workspace path")
        if is_active_pipeline(audit_run.get("status"), audit_run.get("config")):
            raise HTTPException(status_code=409, detail="audit run pipeline is already active")
        await _clear_pipeline_cancel(audit_run_id)
        backend = _normalized_pipeline_backend(settings)
        if backend not in {"workflow-worker", "background-tasks"}:
            backend = "workflow-worker"
        await _mark_audit_run_status(audit_run_id, "queued")
        await _set_pipeline_state(audit_run_id, stage="queued", status="queued")
        await _record_audit_run_event(audit_run_id, "pipeline_queued", {"status": "queued", "backend": backend})
        if backend == "background-tasks":
            background_tasks.add_task(pipeline_executor(runtime).execute, audit_run_id)
        return {"audit_run_id": audit_run_id, "status": "accepted", "backend": backend}

    @router.post("/audit-runs/{audit_run_id}/cancel")
    async def cancel_audit_run(request: Request, audit_run_id: str) -> dict[str, Any]:
        runtime = runtime_provider()
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/cancel", method="POST")
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
        if _should_finalize_cancel(audit_run, removed_container_count):
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

    @router.post("/audit-runs/{audit_run_id}/judge")
    async def judge_audit_run(request: Request, audit_run_id: str) -> dict[str, Any]:
        runtime = runtime_provider()
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/judge", method="POST")
        result = await _judge_audit_run_internal(audit_run_id, runtime)
        if result.get("missing"):
            raise HTTPException(status_code=404, detail="audit run not found")
        return result

    @router.post("/audit-runs/{audit_run_id}/report")
    async def generate_report(request: Request, audit_run_id: str) -> dict[str, Any]:
        runtime = runtime_provider()
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/report", method="POST")
        result = await _generate_report_internal(audit_run_id, settings)
        if result.get("missing"):
            raise HTTPException(status_code=404, detail="audit run not found")
        return result

    @router.get("/audit-runs/{audit_run_id}/evidence")
    async def audit_run_evidence(request: Request, audit_run_id: str) -> list[dict[str, Any]]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        return await _list_evidence(audit_run_id)

    @router.get("/audit-runs/{audit_run_id}/events")
    async def audit_run_events(request: Request, audit_run_id: str) -> list[dict[str, Any]]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        return await _list_audit_run_events(audit_run_id)

    @router.get("/audit-runs/{audit_run_id}/pipeline-status")
    async def audit_run_pipeline_status(request: Request, audit_run_id: str) -> dict[str, Any]:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
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
    async def audit_run_validation_attempts(request: Request, audit_run_id: str) -> list[dict[str, Any]]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        return await _list_validation_attempts(audit_run_id)

    @router.get("/audit-runs/{audit_run_id}/reports")
    async def audit_run_reports(request: Request, audit_run_id: str) -> list[dict[str, Any]]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        return await _list_reports(audit_run_id)

    @router.get("/artifacts/metadata")
    async def artifact_metadata_endpoint(request: Request, path: str = Query(...)) -> dict[str, Any]:
        return await _artifact_metadata_response(request, settings, path)

    @router.get("/artifacts/download")
    async def download_artifact(request: Request, path: str = Query(...)) -> Response:
        return await _artifact_download_response(request, settings, path)

    @router.get("/artifacts/{artifact_id}/download")
    async def download_artifact_by_id(request: Request, artifact_id: str) -> Response:
        try:
            relative_path = relative_path_for_artifact_id(artifact_id)
        except ArtifactAccessError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return await _artifact_download_response(request, settings, relative_path)

    @router.get("/artifacts/{artifact_id}")
    async def artifact_by_id(request: Request, artifact_id: str) -> dict[str, Any]:
        try:
            relative_path = relative_path_for_artifact_id(artifact_id)
        except ArtifactAccessError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        metadata = await _artifact_metadata_response(request, settings, relative_path)
        if metadata["artifact_id"] != artifact_id:
            raise HTTPException(status_code=400, detail="artifact id does not match artifact path")
        return metadata

    @router.get("/reports/{report_id}/download")
    async def download_report(request: Request, report_id: str) -> Response:
        async with SessionLocal() as session:
            report = await session.scalar(select(ReportArtifact).where(ReportArtifact.report_id == report_id))
            if not report:
                raise HTTPException(status_code=404, detail="report not found")
            references = [
                {
                    "kind": "report",
                    "project_id": report.project_id,
                    "audit_run_id": report.audit_run_id,
                    "record_id": report.report_id,
                }
            ]
            if not _principal_can_access_artifact(getattr(request.state, "auth_principal", None), references):
                raise HTTPException(status_code=403, detail="report is outside API key project or audit run scope")
            return await _artifact_download_response(request, settings, report.path, references=references)

    @router.get("/findings/{finding_id}")
    async def get_finding(request: Request, finding_id: str) -> dict[str, Any]:
        detail = await _get_finding_detail(finding_id)
        if not detail:
            raise HTTPException(status_code=404, detail="finding not found")
        _require_finding_access(getattr(request.state, "auth_principal", None), detail["finding"])
        return detail

    @router.post("/findings/{finding_id}/poc")
    async def run_finding_poc(request: Request, finding_id: str, body: RunPocRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        allow_external_network = _effective_sandbox_external_network(settings, body.allow_external_network)
        async with SessionLocal() as session:
            finding = await session.scalar(select(Finding).where(Finding.finding_id == finding_id))
            if not finding:
                raise HTTPException(status_code=404, detail="finding not found")
            _require_finding_access(getattr(request.state, "auth_principal", None), _finding_to_dict(finding))
            audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == finding.audit_run_id))
            if not audit_run:
                raise HTTPException(status_code=404, detail="audit run not found")
            _require_audit_run_access(getattr(request.state, "auth_principal", None), _audit_run_to_dict(audit_run))
            if runtime is None:
                return await proxy_gateway(
                    f"/findings/{finding_id}/poc",
                    method="POST",
                    json={**body.model_dump(), "allow_external_network": allow_external_network},
                )
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
                allow_external_network=allow_external_network,
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
            if _is_sandbox_unavailable_error(str(exc)):
                unavailable = _sandbox_unavailable_result(str(exc), request_body=body.model_dump())
                async with SessionLocal() as session:
                    row = await session.scalar(select(ValidationAttempt).where(ValidationAttempt.attempt_id == attempt.attempt_id))
                    if row:
                        row.status = "unavailable"
                        row.result = {"kind": "poc", **unavailable}
                    session.add(
                        Evidence(
                            evidence_id=str(uuid.uuid4()),
                            finding_id=finding_id,
                            audit_run_id=audit_run_id,
                            kind="poc-unavailable",
                            summary=f"PoC execution unavailable: {exc}",
                            payload=unavailable,
                        )
                    )
                    await session.commit()
                await _record_audit_run_event(
                    audit_run_id,
                    "finding_poc_unavailable",
                    {"finding_id": finding_id, "attempt_id": attempt.attempt_id, **unavailable},
                )
                return {
                    "finding_id": finding_id,
                    "attempt_id": attempt.attempt_id,
                    "status": "unavailable",
                    "matched_expected_exit_code": False,
                    "poc": unavailable,
                    "finding": await _get_finding_detail(finding_id),
                }
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
        templates = agent_template_store().list()
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
        query = select(PlatformAuditEvent)
        if service:
            query = query.where(PlatformAuditEvent.service == service)
        if auth_result:
            query = query.where(PlatformAuditEvent.auth_result == auth_result)
        if status_code:
            query = query.where(PlatformAuditEvent.status_code == status_code)
        query = query.order_by(PlatformAuditEvent.created_at.desc()).limit(limit)
        async with SessionLocal() as session:
            rows = (await session.execute(query)).scalars()
            return [_platform_audit_event_to_dict(row) for row in rows]

    @router.delete("/platform/audit-events")
    async def cleanup_platform_audit_events(
        older_than_days: int | None = Query(default=None, ge=1, le=3650),
        keep_latest: int | None = Query(default=None, ge=0, le=1_000_000),
    ) -> dict[str, Any]:
        days = older_than_days if older_than_days is not None else settings.platform_audit_event_retention_days
        keep = keep_latest if keep_latest is not None else settings.platform_audit_event_max_rows
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with SessionLocal() as session:
            older_result = await session.execute(delete(PlatformAuditEvent).where(PlatformAuditEvent.created_at < cutoff))
            older_deleted = int(older_result.rowcount or 0)
            overflow_deleted = 0
            if keep == 0:
                overflow_result = await session.execute(delete(PlatformAuditEvent))
                overflow_deleted = int(overflow_result.rowcount or 0)
            else:
                retained_ids = list(
                    (
                        await session.execute(
                            select(PlatformAuditEvent.id)
                            .order_by(PlatformAuditEvent.created_at.desc(), PlatformAuditEvent.id.desc())
                            .limit(keep)
                        )
                    ).scalars()
                )
                if retained_ids:
                    overflow_result = await session.execute(
                        delete(PlatformAuditEvent).where(PlatformAuditEvent.id.not_in(retained_ids))
                    )
                    overflow_deleted = int(overflow_result.rowcount or 0)
            await session.commit()
        return {
            "older_than_days": days,
            "cutoff": cutoff.isoformat(),
            "keep_latest": keep,
            "deleted": older_deleted + overflow_deleted,
            "deleted_by_age": older_deleted,
            "deleted_by_overflow": overflow_deleted,
        }

    @router.get("/runtime/templates/agents")
    async def list_agent_templates() -> list[dict[str, Any]]:
        return agent_template_store().list()

    @router.post("/runtime/templates/agents")
    async def upsert_agent_template(body: TemplateBody) -> dict[str, Any]:
        try:
            return agent_template_store().upsert(body.template)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/runtime/templates/mcp")
    async def list_mcp_templates() -> list[dict[str, Any]]:
        return mcp_template_store().list()

    @router.post("/runtime/templates/mcp")
    async def upsert_mcp_template(body: TemplateBody) -> dict[str, Any]:
        try:
            return mcp_template_store().upsert(body.template)
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

    @router.get("/runtime/tool-capabilities")
    async def tool_capabilities() -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway("/runtime/tool-capabilities")
        return await runtime.tool_image_capabilities(mcp_template_store().list())

    @router.get("/runtime/e2e/status")
    async def runtime_e2e_status() -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway("/runtime/e2e/status")
        docker: dict[str, Any]
        try:
            docker = await runtime.docker_health()
        except Exception as exc:
            docker = {"ok": False, "error": str(exc)}
        worker_health = await workflow_worker_health(max_age_seconds=settings.pipeline_worker_heartbeat_ttl_seconds)
        agent_templates = agent_template_store().list()
        mcp_templates = mcp_template_store().list()
        exposed_mock_agents = [
            template.get("name")
            for template in agent_templates
            if "mock-agent" in str(template.get("image") or "")
            or (isinstance(template.get("protocol"), dict) and template["protocol"].get("runtime") == "mock")
        ]
        exposed_mock_mcps = [
            template.get("name")
            for template in mcp_templates
            if "mock-mcp" in str(template.get("image") or "")
        ]
        model_env = {
            "ANTHROPIC_API_KEY": bool(settings.anthropic_api_key),
            "OPENAI_API_KEY": bool(settings.openai_api_key),
            "LOCAL_LLM_API_KEY": bool(settings.local_llm_api_key),
        }
        checks = {
            "docker": bool(docker.get("ok")),
            "workflow_worker": bool(worker_health.get("ok")),
            "demo_templates_hidden": not bool(settings.enable_demo_templates or exposed_mock_agents or exposed_mock_mcps),
            "model_configured": any(model_env.values()),
            "opencode_templates_present": all(
                name in {str(template.get("name")) for template in agent_templates}
                for name in ["opencode-orchestrator", "opencode-validator", "opencode-judger"]
            ),
        }
        return {
            "ok": all(value for key, value in checks.items() if key != "model_configured"),
            "service": settings.service_name,
            "checks": checks,
            "docker": docker,
            "worker_health": worker_health,
            "pipeline_backend": _normalized_pipeline_backend(settings),
            "demo_templates_enabled": settings.enable_demo_templates,
            "exposed_mock_agents": exposed_mock_agents,
            "exposed_mock_mcps": exposed_mock_mcps,
            "model_env": model_env,
            "recommended_gateway_base_url": "http://localhost:8080/gateway",
            "notes": [
                "Without a model API key the smoke script should skip the real OpenCode pipeline segment.",
                "Use /runtime/readiness for full production readiness blockers.",
            ],
        }

    @router.get("/runtime/policy")
    async def runtime_policy() -> dict[str, Any]:
        return {
            "default_container": {
                "memory": settings.default_container_memory,
                "cpus": settings.default_container_cpus,
                "pids_limit": settings.default_container_pids_limit,
                "tmpfs": settings.default_container_tmpfs,
            },
            "platform_audit_events": {
                "retention_days": settings.platform_audit_event_retention_days,
                "max_rows": settings.platform_audit_event_max_rows,
            },
            "local_storage": {
                "artifact_storage_backend": artifact_storage_backend(settings),
                "runtime_package_retention_days": settings.runtime_package_retention_days,
                "upload_staging_retention_days": settings.upload_staging_retention_days,
                "unreferenced_workspace_retention_days": settings.unreferenced_workspace_retention_days,
                "unreferenced_snapshot_retention_days": settings.unreferenced_snapshot_retention_days,
                "cleanup_max_entries": settings.storage_cleanup_max_entries,
            },
            "http_guards": {
                "max_request_body_bytes": settings.max_request_body_bytes,
                "max_upload_bytes": settings.max_upload_bytes,
                "rate_limit_per_minute": settings.rate_limit_per_minute,
                "rate_limit_window_seconds": settings.rate_limit_window_seconds,
            },
            "workspace_import": {
                "max_workspace_files": settings.max_workspace_files,
                "max_workspace_uncompressed_bytes": settings.max_workspace_uncompressed_bytes,
                "allowed_git_url_schemes": [
                    item.strip()
                    for item in settings.allowed_git_url_schemes.split(",")
                    if item.strip()
                ],
                "allowed_git_hosts": [
                    item.strip().lower()
                    for item in settings.allowed_git_hosts.split(",")
                    if item.strip()
                ],
            },
            "pipeline": {
                "execution_backend": settings.pipeline_execution_backend,
                "recovery_on_startup": settings.pipeline_recovery_on_startup,
            },
            "sandbox": {
                "default_runtime": settings.default_sandbox_runtime,
                "enable_gvisor": settings.enable_gvisor,
                "allow_runc_sandbox": settings.allow_runc_sandbox,
            },
        }

    @router.get("/runtime/readiness")
    async def runtime_readiness() -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway("/runtime/readiness")
        auth_enabled = await auth_is_enabled(settings)
        checks: list[dict[str, Any]] = [
            {
                "id": "api_key",
                "title": "API key is configured",
                "status": "pass" if auth_enabled else "fail",
                "detail": {
                    "bootstrap_key_enabled": bool(settings.dieaudit_api_key),
                    "message": "Configure DIEAUDIT_API_KEY or create at least one active persisted API key before exposing the platform.",
                },
                "remediation": [
                    "Set DIEAUDIT_API_KEY for a bootstrap deployment, or create a persisted API key and remove the bootstrap key before production exposure.",
                ],
            },
            {
                "id": "metrics_private",
                "title": "Metrics are protected",
                "status": "pass" if not settings.public_metrics else "fail",
                "detail": "PUBLIC_METRICS=false keeps /metrics behind the API key gate.",
                "remediation": ["Set PUBLIC_METRICS=false unless metrics are exposed only on a trusted internal network."],
            },
            {
                "id": "resource_limits",
                "title": "Dynamic containers have default resource limits",
                "status": "pass"
                if settings.default_container_memory and settings.default_container_cpus and settings.default_container_pids_limit
                else "fail",
                "detail": {
                    "memory": settings.default_container_memory,
                    "cpus": settings.default_container_cpus,
                    "pids_limit": settings.default_container_pids_limit,
                    "tmpfs": settings.default_container_tmpfs,
                },
            },
            {
                "id": "artifact_storage",
                "title": "Artifact storage directory is available",
                "status": "pass",
                "detail": {
                    "backend": artifact_storage_backend(settings),
                    "artifact_root": str(settings.artifact_root),
                },
                "remediation": [],
            },
        ]
        checks.append(_http_guardrails_readiness_check(settings))
        checks.append(_workspace_import_readiness_check(settings))
        worker_health: dict[str, Any] | None = None
        if _normalized_pipeline_backend(settings) == "workflow-worker":
            worker_health = await workflow_worker_health(max_age_seconds=settings.pipeline_worker_heartbeat_ttl_seconds)
        checks.append(_pipeline_backend_readiness_check(settings, worker_health=worker_health))
        async with SessionLocal() as session:
            audit_runs = list((await session.execute(select(AuditRun))).scalars())
            worker_heartbeats = list((await session.execute(select(WorkerHeartbeat))).scalars())
        checks.append(
            _active_pipeline_readiness_check(
                audit_runs,
                worker_heartbeats,
                max_age_seconds=settings.pipeline_worker_heartbeat_ttl_seconds,
            )
        )
        try:
            docker = await runtime.docker_health()
            checks.append(
                {
                    "id": "docker",
                    "title": "Docker runtime is reachable",
                    "status": "pass" if docker.get("ok") else "fail",
                    "detail": {"ping": docker.get("ping"), "version": (docker.get("version") or {}).get("Version")},
                }
            )
        except Exception as exc:
            checks.append({"id": "docker", "title": "Docker runtime is reachable", "status": "fail", "detail": str(exc)})
        try:
            sandbox = await runtime.sandbox_capabilities()
            sandbox_detail = {
                "docker_default_runtime": sandbox.get("docker_default_runtime"),
                "docker_runtimes": sandbox.get("docker_runtimes"),
                "requested_runtime": sandbox.get("requested_runtime"),
                "requested_runtime_available": sandbox.get("requested_runtime_available"),
                "gvisor_available": sandbox.get("gvisor_available"),
                "strong_isolation_available": sandbox.get("strong_isolation_available"),
                "sandbox_execution_available": sandbox.get("sandbox_execution_available"),
                "reason": sandbox.get("reason"),
                "warnings": sandbox.get("warnings"),
            }
            checks.append(
                {
                    "id": "sandbox_isolation",
                    "title": "Docker sandbox execution is available",
                    "status": "pass" if sandbox.get("sandbox_execution_available") else "fail",
                    "detail": sandbox_detail,
                    "remediation": _sandbox_readiness_remediation(sandbox_detail),
                }
            )
        except Exception as exc:
            checks.append({
                "id": "sandbox_isolation",
                "title": "Docker sandbox execution is available",
                "status": "fail",
                "detail": str(exc),
                "remediation": [
                    "Verify Docker Engine is reachable through docker-socket-proxy and DEFAULT_SANDBOX_RUNTIME is available.",
                ],
            })
        knowledge_service = KnowledgeService(settings)
        embedding = await knowledge_service.embedding_health(probe=settings.knowledge_embedding_probe_on_readiness)
        if str(embedding.get("provider") or "").lower() in {"hash", "local-hash", ""}:
            embedding = {
                **embedding,
                "status": "warn",
                "message": "local hash embeddings are available but not semantic; configure openai-compatible embeddings for higher quality RAG",
            }
        checks.append(
            {
                "id": "knowledge_embedding",
                "title": "Knowledge embedding provider is production-ready",
                "status": embedding.get("status", "fail"),
                "detail": embedding,
                "remediation": _embedding_readiness_remediation(embedding),
            }
        )
        vector_store = await knowledge_service.collection_health(probe=settings.knowledge_embedding_probe_on_readiness)
        checks.append(
            {
                "id": "knowledge_vector_store",
                "title": "Knowledge vector collection matches embedding configuration",
                "status": vector_store.get("status", "fail"),
                "detail": vector_store,
                "remediation": _vector_store_readiness_remediation(vector_store),
            }
        )
        agent_templates = agent_template_store().list()
        mcp_templates = mcp_template_store().list()
        tool_capability_result: dict[str, Any] | None = None
        try:
            tool_capability_result = await runtime.tool_image_capabilities(mcp_templates)
        except Exception as exc:
            tool_capability_result = {"ok": False, "error": str(exc), "templates": {}}
        checks.extend(
            _template_readiness_checks(
                agent_templates,
                mcp_templates,
                tool_capability_result,
                include_demo_templates=settings.enable_demo_templates,
            )
        )
        return _summarize_readiness_checks(checks)

    @router.get("/runtime/workers")
    async def runtime_workers() -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway("/runtime/workers")
        workers = await list_worker_heartbeats(service_name=None)
        return {"workers": workers}

    @router.get("/runtime/workers/health")
    async def runtime_workers_health() -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway("/runtime/workers/health")
        return await workflow_worker_health(max_age_seconds=settings.pipeline_worker_heartbeat_ttl_seconds)

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

    @router.get("/runtime/storage")
    async def runtime_storage() -> dict[str, Any]:
        return StorageCleanupService(settings).summary()

    @router.post("/runtime/storage/cleanup")
    async def cleanup_runtime_storage(
        body: StorageCleanupRequest | None = Body(default=None),
    ) -> dict[str, Any]:
        body = body or StorageCleanupRequest()
        service = StorageCleanupService(settings)
        policy = service.policy(
            runtime_package_retention_days=body.runtime_package_retention_days,
            upload_staging_retention_days=body.upload_staging_retention_days,
            unreferenced_workspace_retention_days=body.unreferenced_workspace_retention_days,
            unreferenced_snapshot_retention_days=body.unreferenced_snapshot_retention_days,
            max_entries=body.max_entries,
        )
        async with SessionLocal() as session:
            snapshots = list((await session.execute(select(ProjectSnapshot))).scalars())
            referenced_workspaces = [row.workspace_path for row in snapshots if row.workspace_path]
            referenced_snapshot_artifacts = [row.artifact_path for row in snapshots if row.artifact_path]
        return service.cleanup(
            dry_run=body.dry_run,
            policy=policy,
            referenced_workspace_paths=referenced_workspaces,
            referenced_snapshot_paths=referenced_snapshot_artifacts,
        )

    @router.get("/runtime/tool-images")
    async def tool_images() -> dict[str, Any]:
        agents = agent_template_store().list()
        mcps = mcp_template_store().list()
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
    async def start_agent_run(request: Request, audit_run_id: str, body: StartAgentRunRequest) -> dict[str, Any]:
        principal = getattr(request.state, "auth_principal", None)
        audit_run = await _get_audit_run(audit_run_id)
        if audit_run:
            _require_audit_run_access(principal, audit_run)
            if body.project_id != audit_run["project_id"]:
                raise HTTPException(status_code=400, detail="agent run project_id does not match audit run")
        else:
            allowed_audit_run_ids = _principal_allowed_audit_run_ids(principal)
            if allowed_audit_run_ids and audit_run_id not in allowed_audit_run_ids:
                raise HTTPException(status_code=403, detail="audit run is outside API key project or audit run scope")
            await _require_project_access(principal, body.project_id)
        return await _start_agent_run_impl(audit_run_id, body)

    async def _start_agent_run_impl(audit_run_id: str, body: StartAgentRunRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/agent-runs", method="POST", json=body.model_dump())
        audit_run = None
        with contextlib.suppress(Exception):
            audit_run = await _get_audit_run(audit_run_id)
        input_payload = dict(body.input_payload or {})
        if audit_run:
            input_payload = _with_shared_agent_context(input_payload, audit_run)
        try:
            return await runtime.start_agent_run(
                audit_run_id=audit_run_id,
                project_id=body.project_id,
                agent_name=body.agent_name,
                workspace_host_path=body.workspace_host_path,
                allow_external_network=body.allow_external_network,
                retain_runtime_on_failure=body.retain_runtime_on_failure,
                input_payload=input_payload,
            )
        except (DockerApiError, FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/audit-runs/{audit_run_id}/agent-runtimes/ensure")
    async def ensure_agent_runtime(request: Request, audit_run_id: str, body: EnsureAgentRuntimeRequest) -> dict[str, Any]:
        principal = getattr(request.state, "auth_principal", None)
        audit_run = await _get_audit_run(audit_run_id)
        if audit_run:
            _require_audit_run_access(principal, audit_run)
            if body.project_id != audit_run["project_id"]:
                raise HTTPException(status_code=400, detail="runtime project_id does not match audit run")
        else:
            await _require_project_access(principal, body.project_id)
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/agent-runtimes/ensure", method="POST", json=body.model_dump())
        try:
            return await runtime.ensure_agent_runtime(
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

    @router.post("/internal/agent-runs/{agent_run_id}/transcript-events")
    async def append_agent_transcript_events(agent_run_id: str, body: AgentTranscriptEventsRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        event_payloads = [item.model_dump() for item in body.events]
        if runtime is not None:
            try:
                return await runtime.record_agent_transcript_events(
                    agent_run_id=agent_run_id,
                    runtime_id=body.runtime_id,
                    acp_session_id=body.acp_session_id,
                    events=event_payloads,
                )
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        async with SessionLocal() as session:
            agent_run = await session.scalar(select(AgentRun).where(AgentRun.agent_run_id == agent_run_id))
            if not agent_run:
                raise HTTPException(status_code=404, detail="agent run not found")
            if body.runtime_id:
                agent_run.runtime_id = body.runtime_id
            if body.acp_session_id:
                agent_run.acp_session_id = body.acp_session_id
            session.add_all(
                [
                    AgentTranscriptEvent(
                        agent_run_id=agent_run_id,
                        audit_run_id=agent_run.audit_run_id,
                        runtime_id=item.get("runtime_id") or body.runtime_id,
                        seq=int(item.get("seq") or 0),
                        event_type=str(item.get("event_type") or "event"),
                        session_id=item.get("session_id") or body.acp_session_id,
                        payload=item.get("payload") or {},
                        content_text=item.get("content_text"),
                    )
                    for item in event_payloads
                ]
            )
            await session.commit()
        return {"agent_run_id": agent_run_id, "inserted": len(event_payloads)}

    @router.post("/audit-runs/{audit_run_id}/cleanup-runtime")
    async def cleanup_agent_runtime(request: Request, audit_run_id: str) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/cleanup-runtime", method="POST")
        return await runtime.cleanup_run(audit_run_id)

    @router.get("/audit-runs/{audit_run_id}/deliverables")
    async def audit_run_deliverables(request: Request, audit_run_id: str) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(DeliverableArtifact)
                    .where(DeliverableArtifact.audit_run_id == audit_run_id)
                    .order_by(DeliverableArtifact.kind.asc(), DeliverableArtifact.created_at.asc())
                )
            ).scalars().all()
            runtime_rows = (
                await session.execute(
                    select(AgentRuntime)
                    .where(AgentRuntime.audit_run_id == audit_run_id)
                    .order_by(AgentRuntime.created_at.desc())
                )
            ).scalars().all()
        if not rows:
            generated = await _build_deliverable_package(audit_run_id, settings)
            return generated
        artifacts = [_deliverable_artifact_to_dict(row) for row in rows]
        return {
            "audit_run_id": audit_run_id,
            "root": f"deliverables/{audit_run_id}",
            "artifacts": artifacts,
            "runtimes": [_agent_runtime_to_dict(row) for row in runtime_rows],
        }

    @router.post("/audit-runs/{audit_run_id}/demo")
    async def start_demo(request: Request, audit_run_id: str = "demo-run") -> dict[str, Any]:
        _require_unrestricted_resource_scope(getattr(request.state, "auth_principal", None), "demo audit run")
        if not settings.enable_demo_templates:
            raise HTTPException(status_code=403, detail="demo templates are disabled; set ENABLE_DEMO_TEMPLATES=true to run mock demos")
        workspace = settings.workspace_root / "demo-project"
        workspace.mkdir(parents=True, exist_ok=True)
        demo_file = workspace / "app.py"
        if not demo_file.exists():
            demo_file.write_text("print('hello from vulnerable demo project')\n", encoding="utf-8")
        body = StartAgentRunRequest(
            audit_run_id=audit_run_id,
            project_id="demo-project",
            agent_name="mock-orchestrator",
            workspace_host_path=str(workspace),
            input_payload={"goal": "run demo agent and prove MCP connectivity"},
        )
        return await _start_agent_run_impl(audit_run_id, body)

    @router.post("/audit-runs/{audit_run_id}/opencode-demo")
    async def start_opencode_demo(request: Request, audit_run_id: str = "opencode-demo-run") -> dict[str, Any]:
        _require_unrestricted_resource_scope(getattr(request.state, "auth_principal", None), "demo audit run")
        if not settings.enable_demo_templates:
            raise HTTPException(status_code=403, detail="demo templates are disabled; set ENABLE_DEMO_TEMPLATES=true to run OpenCode demos")
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
            allow_external_network=False,
            input_payload={
                "goal": (
                    "Run a minimal code-audit pass over the demo project. Confirm you can inspect "
                    "the mounted source and report any suspicious vulnerability candidates with file paths."
                )
            },
        )
        return await _start_agent_run_impl(audit_run_id, body)

    @router.get("/audit-runs/{audit_run_id}/agent-runs")
    async def audit_run_agent_runs(request: Request, audit_run_id: str) -> list[dict[str, Any]]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(AgentRun).where(AgentRun.audit_run_id == audit_run_id).order_by(AgentRun.created_at.desc())
                )
            ).scalars()
            return [_agent_run_to_dict(row) for row in rows]

    @router.get("/audit-runs/{audit_run_id}/execution-graph")
    async def audit_run_execution_graph(request: Request, audit_run_id: str) -> dict[str, Any]:
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
        return await _execution_graph(audit_run)

    @router.get("/audit-runs/{audit_run_id}/agent-runs/{agent_run_id}")
    async def audit_run_agent_run(request: Request, audit_run_id: str, agent_run_id: str) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
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
    async def audit_run_agent_run_events(request: Request, audit_run_id: str, agent_run_id: str) -> list[dict[str, Any]]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
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

    @router.get("/audit-runs/{audit_run_id}/agent-runs/{agent_run_id}/transcript-events")
    async def audit_run_agent_run_transcript_events(
        request: Request,
        audit_run_id: str,
        agent_run_id: str,
        after_id: int = Query(default=0, ge=0),
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
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
                    select(AgentTranscriptEvent)
                    .where(
                        AgentTranscriptEvent.agent_run_id == agent_run_id,
                        AgentTranscriptEvent.id > after_id,
                    )
                    .order_by(AgentTranscriptEvent.id.asc())
                    .limit(limit)
                )
            ).scalars().all()
        events = [_agent_transcript_event_to_dict(row) for row in rows]
        return {
            "agent_run_id": agent_run_id,
            "audit_run_id": audit_run_id,
            "events": events,
            "last_id": events[-1]["id"] if events else after_id,
            "has_more": len(events) == limit,
        }

    @router.get("/audit-runs/{audit_run_id}/containers")
    async def audit_run_containers(request: Request, audit_run_id: str) -> list[dict[str, Any]]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/containers")
        return await runtime.containers(audit_run_id)

    @router.get("/audit-runs/{audit_run_id}/containers/{container_id}/logs")
    async def audit_run_container_logs(request: Request, audit_run_id: str, container_id: str) -> Response:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
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
    async def cleanup_audit_run(request: Request, audit_run_id: str) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/cleanup", method="POST")
        return await runtime.cleanup_run(audit_run_id)

    @router.post("/audit-runs/{audit_run_id}/cleanup-inactive-runtime")
    async def cleanup_inactive_audit_run_runtime(request: Request, audit_run_id: str) -> dict[str, Any]:
        await _require_audit_run_id_access(getattr(request.state, "auth_principal", None), audit_run_id)
        runtime = runtime_provider()
        if runtime is None:
            return await proxy_gateway(f"/audit-runs/{audit_run_id}/cleanup-inactive-runtime", method="POST")
        cleanup = getattr(runtime, "cleanup_inactive_agent_runtime", None)
        if cleanup is None:
            raise HTTPException(status_code=400, detail="runtime does not support inactive agent cleanup")
        return await cleanup(audit_run_id)

    @router.post("/audit-runs/{audit_run_id}/sandbox/poc")
    async def run_poc(request: Request, audit_run_id: str, body: RunPocRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        allow_external_network = _effective_sandbox_external_network(settings, body.allow_external_network)
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
        if runtime is None:
            return await proxy_gateway(
                f"/audit-runs/{audit_run_id}/sandbox/poc",
                method="POST",
                json={**body.model_dump(), "allow_external_network": allow_external_network},
            )
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        try:
            result = await runtime.run_poc_container(
                audit_run_id=audit_run_id,
                project_id=audit_run["project_id"],
                image=body.image,
                command=body.command,
                env=body.env,
                workspace_host_path=workspace_path,
                allow_external_network=allow_external_network,
                retain_runtime_on_failure=body.retain_runtime_on_failure,
                timeout_seconds=body.timeout_seconds,
                mount_workspace=body.mount_workspace,
                network_name=body.network_name,
                target_url=body.target_url,
                allow_weak_isolation=body.allow_weak_isolation,
            )
        except (DockerApiError, RuntimeError, ValueError) as exc:
            if _is_sandbox_unavailable_error(str(exc)):
                result = _sandbox_unavailable_result(str(exc), request_body=body.model_dump())
                await _record_audit_run_event(audit_run_id, "poc_run_unavailable", result)
                return result
            await _record_audit_run_event(audit_run_id, "poc_run_failed", {"error": str(exc), "request": body.model_dump()})
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _record_audit_run_event(audit_run_id, "poc_run_completed", result)
        return result

    @router.post("/audit-runs/{audit_run_id}/sandbox/service")
    async def start_sandbox_service(request: Request, audit_run_id: str, body: StartSandboxServiceRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        allow_external_network = _effective_sandbox_external_network(settings, body.allow_external_network)
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
        if runtime is None:
            return await proxy_gateway(
                f"/audit-runs/{audit_run_id}/sandbox/service",
                method="POST",
                json={**body.model_dump(), "allow_external_network": allow_external_network},
            )
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
                allow_external_network=allow_external_network,
                retain_runtime_on_failure=body.retain_runtime_on_failure,
                startup_timeout_seconds=body.startup_timeout_seconds,
                mount_workspace=body.mount_workspace,
                healthcheck_path=body.healthcheck_path,
                allow_weak_isolation=body.allow_weak_isolation,
            )
        except (DockerApiError, RuntimeError, ValueError) as exc:
            if _is_sandbox_unavailable_error(str(exc)):
                result = _sandbox_unavailable_result(str(exc), request_body=body.model_dump())
                await _record_audit_run_event(audit_run_id, "sandbox_service_unavailable", result)
                return result
            await _record_audit_run_event(audit_run_id, "sandbox_service_failed", {"error": str(exc), "request": body.model_dump()})
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _record_audit_run_event(audit_run_id, "sandbox_service_started", result)
        return result

    @router.post("/audit-runs/{audit_run_id}/sandbox/compose")
    async def start_sandbox_compose(request: Request, audit_run_id: str, body: StartSandboxComposeRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        allow_external_network = _effective_sandbox_external_network(settings, body.allow_external_network)
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
        service_request = _sandbox_compose_to_service_request(body)
        if runtime is None:
            return await proxy_gateway(
                f"/audit-runs/{audit_run_id}/sandbox/compose",
                method="POST",
                json={**body.model_dump(), "allow_external_network": allow_external_network},
            )
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        try:
            result = await runtime.start_sandbox_service(
                audit_run_id=audit_run_id,
                project_id=audit_run["project_id"],
                image=service_request.image,
                command=service_request.command,
                env=service_request.env,
                workspace_host_path=workspace_path,
                service_name=service_request.service_name,
                port=service_request.port,
                allow_external_network=allow_external_network,
                retain_runtime_on_failure=service_request.retain_runtime_on_failure,
                startup_timeout_seconds=service_request.startup_timeout_seconds,
                mount_workspace=service_request.mount_workspace,
                healthcheck_path=service_request.healthcheck_path,
                allow_weak_isolation=service_request.allow_weak_isolation,
            )
        except (DockerApiError, RuntimeError, ValueError) as exc:
            if _is_sandbox_unavailable_error(str(exc)):
                result = _sandbox_unavailable_result(str(exc), request_body=body.model_dump())
                await _record_audit_run_event(audit_run_id, "sandbox_compose_unavailable", result)
                return result
            await _record_audit_run_event(audit_run_id, "sandbox_compose_failed", {"error": str(exc), "request": body.model_dump()})
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _record_audit_run_event(
            audit_run_id,
            "sandbox_compose_started",
            {"compose_mode": "single-service", "service_request": service_request.model_dump(), "result": result},
        )
        return {"compose_mode": "single-service", **result}

    @router.post("/audit-runs/{audit_run_id}/validators/scale")
    async def scale_validators(request: Request, audit_run_id: str, body: ValidatorScaleRequest) -> dict[str, Any]:
        runtime = runtime_provider()
        audit_run = await _get_audit_run(audit_run_id)
        if not audit_run:
            raise HTTPException(status_code=404, detail="audit run not found")
        _require_audit_run_access(getattr(request.state, "auth_principal", None), audit_run)
        if body.project_id != audit_run["project_id"]:
            raise HTTPException(status_code=400, detail="validator project_id does not match audit run")
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


def _sandbox_compose_to_service_request(body: StartSandboxComposeRequest) -> StartSandboxServiceRequest:
    try:
        compose = yaml.safe_load(body.compose_yaml)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"invalid compose yaml: {exc}") from exc
    if not isinstance(compose, dict) or not isinstance(compose.get("services"), dict):
        raise HTTPException(status_code=400, detail="compose_yaml must contain a services mapping")
    services = compose["services"]
    if len(services) != 1 and not body.service_name:
        raise HTTPException(status_code=400, detail="multi-service compose requires service_name; only the selected service is started in this version")
    service_name = body.service_name or next(iter(services.keys()))
    if service_name not in services:
        raise HTTPException(status_code=400, detail=f"service not found in compose_yaml: {service_name}")
    if len(services) != 1:
        raise HTTPException(status_code=400, detail="multi-service compose stacks are not yet supported; provide a single target service")
    service = services[service_name]
    if not isinstance(service, dict):
        raise HTTPException(status_code=400, detail="compose service must be a mapping")
    _reject_unsafe_compose_service(service)
    image = str(service.get("image") or "").strip()
    if not image:
        raise HTTPException(status_code=400, detail="compose service image is required")
    command = _compose_command(service.get("command"))
    if not command:
        raise HTTPException(status_code=400, detail="compose service command is required")
    env = _compose_environment(service.get("environment"))
    try:
        port = _compose_port(service)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid compose service port: {exc}") from exc
    healthcheck_path = _compose_healthcheck_path(service)
    return StartSandboxServiceRequest(
        image=image,
        command=command,
        env=env,
        service_name=str(service_name),
        port=port,
        allow_external_network=body.allow_external_network,
        retain_runtime_on_failure=body.retain_runtime_on_failure,
        mount_workspace=body.mount_workspace,
        healthcheck_path=str(healthcheck_path) if healthcheck_path else None,
        startup_timeout_seconds=body.startup_timeout_seconds,
        allow_weak_isolation=body.allow_weak_isolation,
    )


def _reject_unsafe_compose_service(service: dict[str, Any]) -> None:
    forbidden_keys = {"privileged", "pid", "ipc", "cgroup_parent", "network_mode"}
    present = sorted(key for key in forbidden_keys if key in service)
    if present:
        raise HTTPException(status_code=400, detail=f"unsupported unsafe compose keys: {', '.join(present)}")
    volumes = service.get("volumes") or []
    for volume in volumes if isinstance(volumes, list) else []:
        text = str(volume)
        if "/var/run/docker.sock" in text or "\\\\.\\pipe\\docker_engine" in text:
            raise HTTPException(status_code=400, detail="compose service must not mount the Docker socket")


def _compose_command(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value.strip():
        return ["sh", "-lc", value]
    return []


def _compose_environment(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    result: dict[str, str] = {}
    if isinstance(value, list):
        for item in value:
            key, _, val = str(item).partition("=")
            if key:
                result[key] = val
    return result


def _compose_port(service: dict[str, Any]) -> int:
    dieaudit = service.get("x-dieaudit")
    if isinstance(dieaudit, dict) and dieaudit.get("port"):
        return int(dieaudit["port"])
    if service.get("x-dieaudit-port"):
        return int(service["x-dieaudit-port"])
    ports = service.get("ports") or []
    if isinstance(ports, list) and ports:
        raw = str(ports[0]).split("/", 1)[0]
        return int(raw.rsplit(":", 1)[-1])
    expose = service.get("expose") or []
    if isinstance(expose, list) and expose:
        return int(str(expose[0]).split("/", 1)[0])
    return 8080


def _compose_healthcheck_path(service: dict[str, Any]) -> str | None:
    dieaudit = service.get("x-dieaudit")
    if isinstance(dieaudit, dict) and dieaudit.get("healthcheck_path"):
        return str(dieaudit["healthcheck_path"])
    if service.get("x-dieaudit-healthcheck-path"):
        return str(service["x-dieaudit-healthcheck-path"])
    return None


async def _artifact_metadata_response(request: Request, settings: Settings, path: str) -> dict[str, Any]:
    artifact_path, references = await _resolve_authorized_artifact(request, settings, path)
    try:
        metadata = _artifact_store_metadata(settings, artifact_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArtifactAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _upsert_artifact_record(metadata, references)
    return metadata


async def _artifact_download_response(
    request: Request,
    settings: Settings,
    path: str,
    *,
    references: list[dict[str, Any]] | None = None,
) -> Response:
    if references is None:
        artifact_path, references = await _resolve_authorized_artifact(request, settings, path)
    else:
        artifact_path = artifact_absolute_path(settings, path)
    store = ArtifactStore(settings)
    try:
        metadata = _artifact_store_metadata(settings, artifact_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArtifactAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _upsert_artifact_record(metadata, references)
    if artifact_storage_backend(settings) == "minio":
        try:
            blob = store.get_blob(artifact_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return StreamingResponse(
            iter([blob.data]),
            media_type=blob.content_type,
            headers={
                **secure_artifact_headers(),
                "Content-Disposition": f'attachment; filename="{blob.name}"',
            },
        )
    return FileResponse(artifact_path, filename=artifact_path.name, headers=secure_artifact_headers())


def _artifact_store_metadata(settings: Settings, artifact_path: Path) -> dict[str, Any]:
    store = ArtifactStore(settings)
    if artifact_path.exists():
        return store.upload_file(artifact_path)
    return store.metadata_for_path(artifact_path)


async def _resolve_authorized_artifact(
    request: Request,
    settings: Settings,
    path: str,
) -> tuple[Path, list[dict[str, Any]]]:
    try:
        if artifact_storage_backend(settings) == "minio":
            artifact_path = artifact_absolute_path(settings, path)
        else:
            artifact_path = resolve_artifact_path(settings, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArtifactAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    references = await _artifact_references(settings, artifact_path)
    if not references:
        raise HTTPException(status_code=403, detail="artifact is not referenced by a platform record")
    if not _principal_can_access_artifact(getattr(request.state, "auth_principal", None), references):
        raise HTTPException(status_code=403, detail="artifact is outside API key project or audit run scope")
    return artifact_path, references


async def _upsert_artifact_record(metadata: dict[str, Any], references: list[dict[str, Any]]) -> None:
    primary_reference = references[0] if references else {}
    async with SessionLocal() as session:
        row = await session.scalar(select(ArtifactRecord).where(ArtifactRecord.artifact_id == metadata["artifact_id"]))
        values = {
            "artifact_uri": metadata["artifact_uri"],
            "storage_backend": metadata["storage_backend"],
            "path": metadata["path"],
            "content_type": metadata["content_type"],
            "sha256": metadata["sha256"],
            "size": metadata["size"],
            "audit_run_id": primary_reference.get("audit_run_id"),
            "project_id": primary_reference.get("project_id"),
            "metadata_json": {
                "relative_path": metadata["relative_path"],
                "name": metadata["name"],
                "references": references,
            },
        }
        if row:
            for key, value in values.items():
                setattr(row, key, value)
        else:
            session.add(ArtifactRecord(artifact_id=metadata["artifact_id"], **values))
        await session.commit()


def _delete_knowledge_artifact(settings: Settings, artifact_path: Path) -> bool:
    knowledge_root = (settings.artifact_root / "knowledge").resolve()
    try:
        if not artifact_path.exists():
            return False
        if artifact_path != knowledge_root and knowledge_root not in artifact_path.parents:
            return False
        target_dir = artifact_path.parent
        if target_dir != knowledge_root and knowledge_root in target_dir.parents:
            shutil.rmtree(target_dir)
            return True
        artifact_path.unlink()
        return True
    except OSError:
        return False


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


async def _artifact_is_referenced(settings: Settings, artifact_path: Path) -> bool:
    return bool(await _artifact_references(settings, artifact_path))


async def _artifact_references(settings: Settings, artifact_path: Path) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    async with SessionLocal() as session:
        snapshots = (await session.execute(select(ProjectSnapshot).where(ProjectSnapshot.artifact_path.is_not(None)))).scalars()
        for row in snapshots:
            if artifact_path_matches(settings, row.artifact_path, artifact_path):
                references.append(
                    {
                        "kind": "project_snapshot",
                        "project_id": row.project_id,
                        "audit_run_id": None,
                        "record_id": row.snapshot_id,
                    }
                )

        containers = (await session.execute(select(ContainerRun).where(ContainerRun.log_artifact.is_not(None)))).scalars()
        for row in containers:
            if artifact_path_matches(settings, row.log_artifact, artifact_path):
                references.append(
                    {
                        "kind": "container_log",
                        "project_id": row.project_id,
                        "audit_run_id": row.audit_run_id,
                        "record_id": row.container_id,
                    }
                )

        agent_runs = (await session.execute(select(AgentRun).where(AgentRun.artifact_path.is_not(None)))).scalars()
        for row in agent_runs:
            if artifact_path_matches(settings, row.artifact_path, artifact_path):
                references.append(
                    {
                        "kind": "agent_run",
                        "project_id": row.project_id,
                        "audit_run_id": row.audit_run_id,
                        "record_id": row.agent_run_id,
                    }
                )

        evidence_rows = (await session.execute(select(Evidence).where(Evidence.artifact_path.is_not(None)))).scalars()
        for row in evidence_rows:
            if artifact_path_matches(settings, row.artifact_path, artifact_path):
                audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == row.audit_run_id))
                references.append(
                    {
                        "kind": "evidence",
                        "project_id": audit_run.project_id if audit_run else None,
                        "audit_run_id": row.audit_run_id,
                        "record_id": row.evidence_id,
                    }
                )

        findings = (await session.execute(select(Finding))).scalars()
        for row in findings:
            if artifact_path_matches(settings, f"findings/{row.audit_run_id}/{row.finding_id}/finding.md", artifact_path):
                references.append(
                    {
                        "kind": "finding_markdown",
                        "project_id": row.project_id,
                        "audit_run_id": row.audit_run_id,
                        "record_id": row.finding_id,
                    }
                )

        documents = (await session.execute(select(KnowledgeDocument).where(KnowledgeDocument.artifact_path.is_not(None)))).scalars()
        for row in documents:
            if artifact_path_matches(settings, row.artifact_path, artifact_path):
                references.append(
                    {
                        "kind": "knowledge_document",
                        "project_id": row.project_id,
                        "audit_run_id": None,
                        "record_id": row.document_id,
                    }
                )

        reports = (await session.execute(select(ReportArtifact))).scalars()
        for row in reports:
            if artifact_path_matches(settings, row.path, artifact_path):
                references.append(
                    {
                        "kind": "report",
                        "project_id": row.project_id,
                        "audit_run_id": row.audit_run_id,
                        "record_id": row.report_id,
                    }
                )
            if isinstance(row.summary, dict) and artifact_path_matches(settings, row.summary.get("json_path"), artifact_path):
                references.append(
                    {
                        "kind": "report_json",
                        "project_id": row.project_id,
                        "audit_run_id": row.audit_run_id,
                        "record_id": row.report_id,
                    }
                )
    return references


def _principal_can_access_artifact(principal: dict[str, Any] | None, references: list[dict[str, Any]]) -> bool:
    if not references:
        return False
    if not principal or has_scope(principal, "admin"):
        return True
    metadata = principal.get("metadata") if isinstance(principal, dict) else {}
    if not isinstance(metadata, dict):
        return True
    allowed_project_ids = _metadata_id_set(metadata.get("project_ids") or metadata.get("projects"))
    allowed_audit_run_ids = _metadata_id_set(metadata.get("audit_run_ids") or metadata.get("audit_runs"))
    if not allowed_project_ids and not allowed_audit_run_ids:
        return True
    for reference in references:
        project_allowed = not allowed_project_ids or str(reference.get("project_id") or "") in allowed_project_ids
        audit_run_allowed = not allowed_audit_run_ids or str(reference.get("audit_run_id") or "") in allowed_audit_run_ids
        if project_allowed and audit_run_allowed:
            return True
    return False


def _principal_metadata(principal: dict[str, Any] | None) -> dict[str, Any]:
    metadata = principal.get("metadata") if isinstance(principal, dict) else {}
    return metadata if isinstance(metadata, dict) else {}


def _principal_allowed_project_ids(principal: dict[str, Any] | None) -> set[str]:
    if not principal or has_scope(principal, "admin"):
        return set()
    metadata = _principal_metadata(principal)
    return _metadata_id_set(metadata.get("project_ids") or metadata.get("projects"))


def _principal_allowed_audit_run_ids(principal: dict[str, Any] | None) -> set[str]:
    if not principal or has_scope(principal, "admin"):
        return set()
    metadata = _principal_metadata(principal)
    return _metadata_id_set(metadata.get("audit_run_ids") or metadata.get("audit_runs"))


def _principal_has_resource_limits(principal: dict[str, Any] | None) -> bool:
    return bool(_principal_allowed_project_ids(principal) or _principal_allowed_audit_run_ids(principal))


def _principal_can_access_audit_run(principal: dict[str, Any] | None, audit_run: dict[str, Any] | AuditRun | None) -> bool:
    if not audit_run:
        return False
    if not principal or has_scope(principal, "admin"):
        return True
    allowed_project_ids = _principal_allowed_project_ids(principal)
    allowed_audit_run_ids = _principal_allowed_audit_run_ids(principal)
    if not allowed_project_ids and not allowed_audit_run_ids:
        return True
    audit_run_id = _resource_attr(audit_run, "audit_run_id")
    project_id = _resource_attr(audit_run, "project_id")
    project_allowed = not allowed_project_ids or project_id in allowed_project_ids
    audit_run_allowed = not allowed_audit_run_ids or audit_run_id in allowed_audit_run_ids
    return project_allowed and audit_run_allowed


async def _principal_can_access_project(principal: dict[str, Any] | None, project_id: str | None) -> bool:
    if not project_id:
        return False
    if not principal or has_scope(principal, "admin"):
        return True
    allowed_project_ids = _principal_allowed_project_ids(principal)
    allowed_audit_run_ids = _principal_allowed_audit_run_ids(principal)
    if not allowed_project_ids and not allowed_audit_run_ids:
        return True
    if allowed_project_ids and project_id not in allowed_project_ids:
        return False
    if not allowed_audit_run_ids:
        return True
    async with SessionLocal() as session:
        audit_run_id = await session.scalar(
            select(AuditRun.audit_run_id)
            .where(AuditRun.project_id == project_id, AuditRun.audit_run_id.in_(allowed_audit_run_ids))
            .limit(1)
        )
    return bool(audit_run_id)


async def _require_project_access(principal: dict[str, Any] | None, project_id: str) -> None:
    if not await _principal_can_access_project(principal, project_id):
        raise HTTPException(status_code=403, detail="project is outside API key project or audit run scope")


def _require_audit_run_access(principal: dict[str, Any] | None, audit_run: dict[str, Any] | AuditRun | None) -> None:
    if not _principal_can_access_audit_run(principal, audit_run):
        raise HTTPException(status_code=403, detail="audit run is outside API key project or audit run scope")


async def _require_audit_run_id_access(principal: dict[str, Any] | None, audit_run_id: str) -> dict[str, Any]:
    audit_run = await _get_audit_run(audit_run_id)
    if not audit_run:
        raise HTTPException(status_code=404, detail="audit run not found")
    _require_audit_run_access(principal, audit_run)
    return audit_run


def _require_finding_access(principal: dict[str, Any] | None, finding: dict[str, Any] | Finding | None) -> None:
    if not finding:
        raise HTTPException(status_code=404, detail="finding not found")
    audit_run = {
        "audit_run_id": _resource_attr(finding, "audit_run_id"),
        "project_id": _resource_attr(finding, "project_id"),
    }
    _require_audit_run_access(principal, audit_run)


def _require_unrestricted_resource_scope(principal: dict[str, Any] | None, action: str) -> None:
    if _principal_has_resource_limits(principal):
        raise HTTPException(status_code=403, detail=f"{action} requires unrestricted API key resource scope")


def _effective_sandbox_external_network(settings: Settings, requested: bool) -> bool:
    if requested and not settings.allow_sandbox_external_network:
        raise HTTPException(
            status_code=403,
            detail="sandbox external network is disabled by platform policy; set ALLOW_SANDBOX_EXTERNAL_NETWORK=true to permit it",
        )
    return bool(requested)


def _effective_agent_external_network(audit_run: dict[str, Any], settings: Settings) -> bool:
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    return bool(config.get("allow_agent_external_network", settings.allow_agent_external_network))


def _is_sandbox_unavailable_error(message: str) -> bool:
    normalized = message.lower()
    return any(
        token in normalized
        for token in (
            "sandbox execution is not available",
            "sandbox execution requires",
            "allow_runc_sandbox",
            "docker runc runtime",
            "gvisor",
            "runsc",
            "configured sandbox runtime",
        )
    )


def _sandbox_unavailable_result(message: str, *, request_body: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "unavailable",
        "reason": message,
        "request": request_body,
    }


def _resource_attr(resource: dict[str, Any] | Any, key: str) -> str:
    if isinstance(resource, dict):
        return str(resource.get(key) or "")
    return str(getattr(resource, key, "") or "")


def _metadata_id_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return set()


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


def _should_finalize_cancel(audit_run: dict[str, Any], removed_container_count: int) -> bool:
    return removed_container_count == 0 or not is_active_pipeline(audit_run.get("status"), audit_run.get("config"))


async def _get_project(project_id: str) -> dict[str, Any] | None:
    async with SessionLocal() as session:
        project = await session.scalar(select(Project).where(Project.project_id == project_id))
        return _project_to_dict(project) if project else None


async def _get_audit_run(audit_run_id: str) -> dict[str, Any] | None:
    async with SessionLocal() as session:
        audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
        return _audit_run_to_dict(audit_run) if audit_run else None


async def _list_findings(audit_run_id: str) -> list[dict[str, Any]]:
    await _sync_whiteboard_candidate_findings(audit_run_id)
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(Finding).where(Finding.audit_run_id == audit_run_id).order_by(Finding.created_at.asc()))
        ).scalars()
        return [_finding_to_dict(row) for row in rows]


async def _sync_whiteboard_candidate_findings(audit_run_id: str) -> dict[str, Any]:
    created = 0
    linked = 0
    candidate_card_types = {"candidate_vulnerability", "candidate-vulnerability"}
    async with SessionLocal() as session:
        cards = (
            await session.execute(
                select(WhiteboardCard)
                .where(WhiteboardCard.audit_run_id == audit_run_id)
                .where(WhiteboardCard.card_type.in_(candidate_card_types))
                .order_by(WhiteboardCard.created_at.asc())
            )
        ).scalars().all()
        for card in cards:
            if card.finding_id:
                linked += 1
                continue
            metadata = card.metadata_json or {}
            source = str(metadata.get("source") or card.author or "whiteboard")[:64]
            identity = finding_identity(
                title=card.title,
                source=source,
                file_path=card.file_path,
                line_start=card.line_start,
                rule_id=str(metadata.get("rule_id") or "") or None,
            )
            existing = await find_existing_finding(session, audit_run_id=audit_run_id, identity=identity)
            if existing:
                card.finding_id = existing.finding_id
                linked += 1
                continue
            finding = Finding(
                finding_id=str(uuid.uuid4()),
                audit_run_id=audit_run_id,
                project_id=card.project_id,
                title=identity["title"],
                severity=_whiteboard_finding_severity(card),
                status="candidate",
                file_path=identity["file_path"],
                line_start=identity["line_start"],
                line_end=card.line_end,
                rule_id=identity["rule_id"],
                description=card.content,
                source=identity["source"],
                raw={
                    "whiteboard_card_id": card.card_id,
                    "whiteboard_status": card.status,
                    "whiteboard_author": card.author,
                    "whiteboard_metadata": metadata,
                    "agent_run_id": card.agent_run_id,
                },
            )
            session.add(finding)
            session.add(
                Evidence(
                    evidence_id=str(uuid.uuid4()),
                    finding_id=finding.finding_id,
                    audit_run_id=audit_run_id,
                    kind="whiteboard-card",
                    summary=card.content,
                    payload={
                        "card_id": card.card_id,
                        "title": card.title,
                        "confidence": card.confidence,
                        "metadata": metadata,
                    },
                )
            )
            card.finding_id = finding.finding_id
            created += 1
        if created or linked:
            session.add(
                AuditRunEvent(
                    audit_run_id=audit_run_id,
                    event_type="whiteboard_findings_synced",
                    payload={"created": created, "linked": linked, "candidate_cards": len(cards)},
                )
            )
        await session.commit()
    return {"created": created, "linked": linked}


def _whiteboard_finding_severity(card: WhiteboardCard) -> str:
    metadata = card.metadata_json or {}
    for key in ("severity", "risk", "priority"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()[:32]
    content = (card.content or "").lower()
    for value in ("critical", "high", "medium", "low", "info"):
        if f"severity: {value}" in content or f'"severity": "{value}"' in content:
            return value
    return "unknown"


async def _list_code_analysis_tasks(audit_run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(CodeAnalysisTask)
                .where(CodeAnalysisTask.audit_run_id == audit_run_id)
                .order_by(CodeAnalysisTask.created_at.asc(), CodeAnalysisTask.task_id.asc())
            )
        ).scalars()
        return [_code_analysis_task_to_dict(row) for row in rows]


async def _list_evidence(audit_run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(Evidence).where(Evidence.audit_run_id == audit_run_id).order_by(Evidence.created_at.asc()))
        ).scalars()
        return [_evidence_to_dict(row) for row in rows]


async def _list_dependency_records(audit_run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(DependencyRecord)
                .where(DependencyRecord.audit_run_id == audit_run_id)
                .order_by(DependencyRecord.ecosystem.asc(), DependencyRecord.name.asc(), DependencyRecord.version.asc())
            )
        ).scalars()
        return [_dependency_record_to_dict(row) for row in rows]


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


async def _replace_dependency_records(
    *,
    session: Any,
    audit_run_id: str,
    project_id: str,
    packages: list[Any],
    vulnerabilities: list[Any],
) -> int:
    vulnerability_map = _dependency_vulnerability_map(vulnerabilities)
    await session.execute(delete(DependencyRecord).where(DependencyRecord.audit_run_id == audit_run_id))
    created = 0
    seen: set[tuple[str, str, str | None, str | None]] = set()
    for item in packages:
        if not isinstance(item, dict):
            continue
        ecosystem = str(item.get("ecosystem") or "unknown").strip() or "unknown"
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        version = str(item.get("version")).strip() if item.get("version") is not None else None
        manifest = str(item.get("manifest")).strip() if item.get("manifest") is not None else None
        dedupe_key = (ecosystem.lower(), name.lower(), version, manifest)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        vulns = vulnerability_map.get(_dependency_key(item), [])
        session.add(
            DependencyRecord(
                dependency_id=str(uuid.uuid4()),
                audit_run_id=audit_run_id,
                project_id=project_id,
                ecosystem=ecosystem,
                name=name,
                version=version,
                manifest=manifest,
                vulnerability_count=len(vulns),
                vulnerabilities=vulns,
            )
        )
        created += 1
    return created


def _dependency_vulnerability_map(vulnerabilities: list[Any]) -> dict[tuple[str, str, str | None], list[dict[str, Any]]]:
    result: dict[tuple[str, str, str | None], list[dict[str, Any]]] = {}
    for item in vulnerabilities:
        if not isinstance(item, dict):
            continue
        package = item.get("package")
        if not isinstance(package, dict):
            continue
        result.setdefault(_dependency_key(package), []).append(item)
    return result


def _dependency_key(package: dict[str, Any]) -> tuple[str, str, str | None]:
    ecosystem = str(package.get("ecosystem") or "unknown").strip().lower()
    name = str(package.get("name") or "").strip().lower()
    version = str(package.get("version")).strip() if package.get("version") is not None else None
    return ecosystem, name, version


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


async def _count_rows(session: Any, model: Any) -> int:
    value = await session.scalar(select(func.count()).select_from(model))
    return int(value or 0)


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
            session.add(AgentRunEvent(agent_run_id=agent_run.agent_run_id, event_type=event_type, payload_json=payload, payload=payload))
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
            session.add(AgentRunEvent(agent_run_id=agent_run.agent_run_id, event_type="pipeline_summary", payload_json=summary, payload=summary))
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

    try:
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
    except Exception as exc:
        osv_result = {"ok": False, "result": {"ok": False, "available": False, "error": str(exc), "packages": [], "vulnerabilities": [], "findings": []}}
        await _record_pipeline_event(audit_run_id, "sca_osv_failed", osv_result)
    result = osv_result.get("result", {})
    artifact_path = None
    if isinstance(sbom_result, dict):
        artifact_path = ((sbom_result.get("result") or {}).get("artifact_path") if sbom_result.get("result") else None)
    packages = result.get("packages", []) if isinstance(result, dict) else []
    vulnerabilities = result.get("vulnerabilities", []) if isinstance(result, dict) else []
    async with SessionLocal() as session:
        dependency_records = await _replace_dependency_records(
            session=session,
            audit_run_id=audit_run_id,
            project_id=project_id,
            packages=packages,
            vulnerabilities=vulnerabilities,
        )
        await session.commit()
    created = await _ingest_tool_findings(
        audit_run_id=audit_run_id,
        project_id=project_id,
        source="sca-mcp",
        findings=result.get("findings", []) if isinstance(result, dict) else [],
        evidence_kind="sca-result",
        artifact_path=artifact_path,
        tool_execution={
            "sbom": _tool_result_metadata((sbom_result or {}).get("result") if isinstance(sbom_result, dict) else None),
            "osv": _tool_result_metadata(result),
        },
    )
    sbom_payload = (sbom_result or {}).get("result") if isinstance(sbom_result, dict) else {}
    status = _sca_status(sbom_payload if isinstance(sbom_payload, dict) else {}, result if isinstance(result, dict) else {}, packages)
    summary = {
        "ok": status["ok"],
        "status": status["status"],
        "reason": status["reason"],
        "coverage": {
            "package_count": len(packages),
            "dependency_record_count": dependency_records,
            "vulnerable_package_count": sum(1 for item in vulnerabilities if isinstance(item, dict)),
            "vulnerability_count": len(vulnerabilities),
            "sbom_available": bool((sbom_payload or {}).get("ok")) if isinstance(sbom_payload, dict) else False,
            "osv_available": bool(result.get("available", osv_result.get("ok"))) if isinstance(result, dict) else bool(osv_result.get("ok")),
        },
        "packages": len(packages),
        "vulnerabilities": len(vulnerabilities),
        "dependency_records": dependency_records,
        "findings_created": created,
        "sbom": sbom_result,
        "osv": _tool_result_metadata(result),
    }
    await _record_pipeline_event(audit_run_id, "sca_completed", summary)
    return summary


async def _run_structure_discovery(
    audit_run_id: str,
    project_id: str,
    workspace_path: str,
    runtime: Any,
    audit_run: dict[str, Any],
) -> dict[str, Any]:
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    settings = get_settings()
    common_dir = settings.artifact_root / "common" / audit_run_id
    common_dir.mkdir(parents=True, exist_ok=True)
    structure_path = common_dir / "STRUCTURE.md"
    inventory = _workspace_structure_inventory(Path(workspace_path))
    decompiled = {"enabled": False, "artifacts": [], "count": 0}
    if bool(config.get("enable_decompilation", True)):
        decompiled = DecompilerService(
            workspace_path,
            output_dir=str(config.get("decompiled_source_dir") or ".dieaudit/decompiled"),
            max_artifact_size_mb=int(config.get("decompile_max_artifact_size_mb") or 200),
            timeout_seconds=int(config.get("decompile_timeout_seconds") or 300),
            max_artifacts=int(config.get("decompile_max_artifacts") or 50),
        ).decompile()
    structure_path.write_text(
        _render_structure_markdown(
            audit_run_id=audit_run_id,
            project_id=project_id,
            workspace_path=workspace_path,
            inventory=inventory,
            decompiled=decompiled,
        ),
        encoding="utf-8",
    )
    result: dict[str, Any] = {
        "ok": True,
        "available": True,
        "path": str(structure_path),
        "relative_path": f"common/{audit_run_id}/STRUCTURE.md",
        "agent_path": "/artifacts/common/STRUCTURE.md",
        "inventory": inventory,
        "decompiled": decompiled,
        "agent_run": None,
    }
    await _record_pipeline_event(audit_run_id, "structure_discovery_bootstrap_completed", _compact_event_payload(result))
    if bool(config.get("enable_structure_discovery_agent", True)) and runtime is not None:
        agent_name = str(config.get("structure_discovery_agent_name") or config.get("agent_name") or "opencode-orchestrator")
        try:
            agent_result = await runtime.start_agent_run(
                audit_run_id=audit_run_id,
                project_id=project_id,
                agent_name=agent_name,
                workspace_host_path=workspace_path,
                allow_external_network=_effective_agent_external_network(audit_run, get_settings()),
                retain_runtime_on_failure=bool(audit_run.get("retain_runtime_on_failure")),
                input_payload={
                    "goal": (
                        "Explore the project architecture and update /artifacts/common/STRUCTURE.md. "
                        "Describe core components, entrypoints, trust boundaries, data flows, and security-sensitive components."
                    ),
                    "audit_phase": "structure-discovery",
                    "structure": {
                        "path": "/artifacts/common/STRUCTURE.md",
                        "instruction": "Read the workspace read-only and update this shared markdown file in place.",
                    },
                },
            )
            result["agent_run"] = _compact_event_payload(agent_result)
            if isinstance(agent_result, dict) and (agent_result.get("error") or str(agent_result.get("status") or "").lower() == "failed"):
                result["ok"] = False
        except Exception as exc:
            result["ok"] = False
            result["agent_error"] = str(exc)
    await _record_pipeline_event(audit_run_id, "structure_discovery_completed", _compact_event_payload(result))
    return result


def _workspace_structure_inventory(workspace: Path) -> dict[str, Any]:
    markers = {
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        "Dockerfile",
        "docker-compose.yml",
        "compose.yml",
    }
    ignored = {".git", "node_modules", ".venv", "__pycache__", "target", "dist", "build"}
    files: list[str] = []
    directories: set[str] = set()
    marker_hits: list[str] = []
    critical_paths: dict[str, list[str]] = {
        "entrypoints": [],
        "routes": [],
        "auth": [],
        "data": [],
        "files": [],
        "network": [],
        "deserialization": [],
    }
    keywords = {
        "entrypoints": ("main", "startup", "bootstrap", "server", "app."),
        "routes": ("route", "router", "controller", "handler", "endpoint", "api"),
        "auth": ("auth", "login", "session", "jwt", "permission", "role", "policy"),
        "data": ("sql", "query", "repository", "dao", "mapper", "database", "model"),
        "files": ("upload", "download", "file", "path", "archive", "extract"),
        "network": ("http", "request", "fetch", "url", "client", "socket"),
        "deserialization": ("deserialize", "pickle", "yaml", "xml", "protobuf", "json"),
    }
    try:
        for path in workspace.rglob("*"):
            if any(part in ignored for part in path.parts):
                continue
            rel = path.relative_to(workspace).as_posix()
            if path.is_dir():
                if rel.count("/") <= 1:
                    directories.add(rel)
                continue
            if path.name in markers:
                marker_hits.append(rel)
            if len(files) < 200:
                files.append(rel)
            lowered = rel.lower()
            for category, terms in keywords.items():
                if len(critical_paths[category]) < 40 and any(term in lowered for term in terms):
                    critical_paths[category].append(rel)
    except OSError:
        pass
    return {
        "markers": sorted(marker_hits),
        "top_directories": sorted(directories)[:80],
        "sample_files": files[:200],
        "critical_paths": {key: sorted(value) for key, value in critical_paths.items() if value},
    }


def _render_structure_markdown(
    *,
    audit_run_id: str,
    project_id: str,
    workspace_path: str,
    inventory: dict[str, Any],
    decompiled: dict[str, Any] | None = None,
) -> str:
    lines = [
        "# STRUCTURE",
        "",
        f"- AuditRun: `{audit_run_id}`",
        f"- Project: `{project_id}`",
        f"- Workspace: `{workspace_path}`",
        "",
        "## Detected Project Markers",
    ]
    lines.extend([f"- `{item}`" for item in inventory.get("markers") or []] or ["- No common build markers detected."])
    lines.extend(["", "## Top Directories"])
    lines.extend([f"- `{item}`" for item in inventory.get("top_directories") or []] or ["- No directories sampled."])
    lines.extend(["", "## Sample Files"])
    lines.extend([f"- `{item}`" for item in inventory.get("sample_files") or []] or ["- No files sampled."])
    lines.extend(["", "## Architecture And Critical Flow Hints"])
    critical_paths = inventory.get("critical_paths") if isinstance(inventory.get("critical_paths"), dict) else {}
    if critical_paths:
        for category, paths in critical_paths.items():
            lines.extend([f"", f"### {category}"])
            lines.extend([f"- `{item}`" for item in paths[:40]])
    else:
        lines.append("- No keyword-based critical paths detected in bootstrap scan.")
    lines.extend(["", "## Decompiled Artifacts"])
    decompiled_artifacts = (decompiled or {}).get("artifacts") if isinstance(decompiled, dict) else []
    if decompiled_artifacts:
        for item in decompiled_artifacts:
            if not isinstance(item, dict):
                continue
            lines.extend(
                [
                    f"- `{item.get('original_path')}`",
                    f"  - artifact_id: `{item.get('artifact_id')}`",
                    f"  - tool: `{item.get('tool')}`",
                    f"  - status: `{item.get('status')}`",
                    f"  - output: `{item.get('workspace_output_path')}`",
                    f"  - language_hint: `{item.get('language_hint')}`",
                    f"  - graph_indexable: `{item.get('graph_indexable')}`",
                ]
            )
            if item.get("error"):
                lines.append(f"  - error: `{str(item.get('error'))[:500]}`")
    else:
        lines.append("- No packaged artifacts were decompiled.")
    lines.extend(["", "## Recommended Code Graph Indexing"])
    lines.append("- Use `codebase-memory-mcp.index_repository` with `repo_path` set to `/workspace`.")
    if decompiled_artifacts:
        for item in decompiled_artifacts:
            if isinstance(item, dict) and item.get("graph_indexable"):
                lines.append(f"- Include decompiled output `{item.get('workspace_output_path')}` when investigating `{item.get('artifact_id')}`.")
    lines.extend(
        [
            "",
            "## Agent Notes",
            "",
            "This file is a shared starting point. Structure-discovery Agents should extend it with architecture, entrypoints, trust boundaries, data flows, decompiled source usage, and security-sensitive components.",
            "",
        ]
    )
    return "\n".join(lines)


def _with_shared_agent_context(payload: dict[str, Any], audit_run: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload or {})
    audit_run_id = str(audit_run.get("audit_run_id") or "")
    if audit_run_id:
        settings = get_settings()
        result.setdefault(
            "structure",
            {
                "path": "/artifacts/common/STRUCTURE.md",
                "artifact_path": str(settings.artifact_root / "common" / audit_run_id / "STRUCTURE.md"),
                "instruction": "Read STRUCTURE.md before analysis and update it only during structure-discovery.",
            },
        )
    result.setdefault(
        "codebase_memory",
        {
            "mcp": "codebase-memory-mcp",
            "repo_path": "/workspace",
            "cache_dir": "/artifacts/codebase-memory",
            "instruction": (
                "Use codebase-memory-mcp for graph-backed analysis. Call index_repository for /workspace when graph context "
                "is needed or missing; use get_architecture before broad planning, then search_graph, trace_path, "
                "query_graph, get_code_snippet, detect_changes, and search_code for focused security analysis."
            ),
        },
    )
    result.setdefault(
        "agent_collaboration",
        {
            "whiteboard_mcp": "whiteboard-mcp",
            "codebase_memory_mcp": "codebase-memory-mcp",
            "instruction": (
                "Use whiteboard-mcp for shared cards, subscriptions, notifications, and help requests. "
                "Use codebase-memory-mcp for architecture, route, symbol, source/sink, call-chain, and graph queries whenever available."
            ),
        },
    )
    return result


async def _run_semgrep_mcp(
    audit_run_id: str,
    project_id: str,
    workspace_path: str,
    runtime: Any,
    audit_run: dict[str, Any],
) -> dict[str, Any]:
    allow_network = bool(audit_run.get("config", {}).get("allow_semgrep_external_network", True))
    mcp_result = await runtime.run_mcp_tool(
        audit_run_id=audit_run_id,
        project_id=project_id,
        mcp_name="semgrep-mcp",
        tool_path="/tools/semgrep_scan",
        workspace_host_path=workspace_path,
        payload={"config": "auto", "output_format": "json", "timeout_seconds": 300},
        allow_external_network=allow_network,
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
        tool_execution=_tool_result_metadata(result),
    )
    status = _semgrep_status(result if isinstance(result, dict) else {"ok": bool(mcp_result.get("ok"))})
    summary = {
        "ok": status["ok"],
        "status": status["status"],
        "reason": status["reason"],
        "available": result.get("available") if isinstance(result, dict) else None,
        "artifact_path": result.get("artifact_path") if isinstance(result, dict) else None,
        "artifact": result.get("artifact") if isinstance(result, dict) else None,
        "findings_created": created,
        "raw_finding_count": len(result.get("findings") or []) if isinstance(result, dict) else 0,
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
    tool_execution: dict[str, Any] | None = None,
) -> int:
    created = 0
    async with SessionLocal() as session:
        for item in findings:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("rule_id") or f"{source} finding")[:255]
            identity = finding_identity(
                title=title,
                source=item.get("source") or source,
                file_path=item.get("file_path"),
                line_start=item.get("line_start"),
                rule_id=item.get("rule_id"),
            )
            if await find_existing_finding(session, audit_run_id=audit_run_id, identity=identity):
                continue
            finding = Finding(
                finding_id=str(uuid.uuid4()),
                audit_run_id=audit_run_id,
                project_id=project_id,
                title=identity["title"],
                severity=str(item.get("severity") or "unknown").lower(),
                status=str(item.get("status") or "candidate"),
                file_path=identity["file_path"],
                line_start=identity["line_start"],
                line_end=_optional_int(item.get("line_end")),
                rule_id=identity["rule_id"],
                description=str(item["description"]) if item.get("description") else None,
                source=identity["source"],
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
                    payload=_tool_evidence_payload(item, tool_execution),
                )
            )
            created += 1
        await session.commit()
    return created


def _tool_result_metadata(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    keys = {
        "artifact",
        "artifact_path",
        "available",
        "command",
        "cwd",
        "error",
        "exit_code",
        "ok",
        "timeout_seconds",
        "tool",
    }
    return {key: result[key] for key in keys if key in result}


def _tool_evidence_payload(finding: dict[str, Any], tool_execution: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(finding)
    if tool_execution:
        payload["tool_execution"] = _compact_event_payload(tool_execution)
    return payload


def _sca_status(sbom_result: dict[str, Any], osv_result: dict[str, Any], packages: list[Any]) -> dict[str, Any]:
    if sbom_result and sbom_result.get("available") is False:
        return {"ok": False, "status": "syft_unavailable", "reason": sbom_result.get("error") or "syft unavailable"}
    if osv_result.get("available") is False or osv_result.get("ok") is False:
        return {"ok": False, "status": "osv_unreachable", "reason": osv_result.get("error") or "OSV query failed"}
    if not packages:
        return {"ok": True, "status": "no_dependencies", "reason": "no supported dependency manifests with pinned versions were detected"}
    return {"ok": True, "status": "completed", "reason": None}


def _semgrep_status(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("available") is False:
        return {"ok": False, "status": "unavailable", "reason": result.get("error") or "semgrep unavailable"}
    if result.get("ok") is False:
        return {"ok": False, "status": "failed", "reason": result.get("error") or result.get("stderr") or "semgrep scan failed"}
    findings = result.get("findings") if isinstance(result.get("findings"), list) else []
    if findings:
        return {"ok": True, "status": "has_findings", "reason": None}
    return {"ok": True, "status": "no_findings", "reason": None}


def _codebase_memory_context() -> dict[str, Any]:
    return {
        "mcp": "codebase-memory-mcp",
        "repo_path": "/workspace",
        "cache_dir": "/artifacts/codebase-memory",
        "tools": [
            "index_repository",
            "get_architecture",
            "search_graph",
            "trace_path",
            "query_graph",
            "get_code_snippet",
            "detect_changes",
            "search_code",
        ],
        "instruction": (
            "Call index_repository for /workspace when graph context is needed or missing. "
            "Use get_architecture before broad planning, then search_graph, trace_path, query_graph, "
            "get_code_snippet, detect_changes, and search_code for focused security analysis."
        ),
    }


async def _judge_audit_run_internal(audit_run_id: str, runtime: Any) -> dict[str, Any]:
    audit_run = await _get_audit_run(audit_run_id)
    if not audit_run:
        return {"missing": True}
    workspace_path = audit_run.get("config", {}).get("workspace_host_path")
    findings = await _list_findings(audit_run_id)
    agent_results: list[dict[str, Any]] = []
    if findings and workspace_path:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        max_parallel = max(1, int(config.get("max_parallel_judgers") or 2))
        semaphore = asyncio.Semaphore(max_parallel)

        async def judge_one(finding: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await _run_judger_finding_internal(audit_run_id, runtime, audit_run, finding)

        agent_results = await asyncio.gather(*(judge_one(finding) for finding in findings))
    return await _complete_judgement_internal(audit_run_id, agent_results)


async def _run_judger_finding_internal(audit_run_id: str, runtime: Any, audit_run: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any]:
    workspace_path = audit_run.get("config", {}).get("workspace_host_path")
    if not workspace_path:
        return {"finding_id": str(finding.get("finding_id") or ""), "status": "failed", "error": "audit run has no workspace path"}
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    finding_id = str(finding.get("finding_id") or "")
    evidence = await _list_evidence(audit_run_id)
    attempts = await _list_validation_attempts(audit_run_id)
    finding_evidence = [item for item in evidence if str(item.get("finding_id")) == finding_id]
    finding_attempts = [item for item in attempts if str(item.get("finding_id")) == finding_id]
    try:
        _ensure_finding_state_markdown(
            audit_run_id,
            finding,
            evidence=finding_evidence,
            attempts=finding_attempts,
        )
        agent_result = await runtime.start_agent_run(
            audit_run_id=audit_run_id,
            project_id=audit_run["project_id"],
            agent_name=str(config.get("judger_agent_name") or "opencode-judger"),
            workspace_host_path=workspace_path,
            allow_external_network=_effective_agent_external_network(audit_run, get_settings()),
            retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
            input_payload={
                "goal": (
                    "Judge this single Finding after source-to-sink analysis and validation. Return JSON with decisions: "
                    "[{\"finding_id\":\"...\",\"status\":\"confirmed|false_positive|needs_review\",\"reason\":\"...\"}]."
                ),
                "audit_phase": "judgement",
                "finding": finding,
                "evidence": finding_evidence,
                "validation_attempts": finding_attempts,
                "finding_artifact_contract": _finding_artifact_contract(audit_run_id, finding_id, "judger"),
                "codebase_memory": _codebase_memory_context(),
            },
        )
        agent_run_id = str(agent_result.get("agent_run_id") or agent_result.get("run_id") or "")
        decisions = await _extract_judger_decisions(agent_run_id) if agent_run_id else []
        await _write_finding_agent_report(
            audit_run_id=audit_run_id,
            finding_id=finding_id,
            stage="judger",
            agent_run_id=agent_run_id or None,
            title="Judger Report",
            payload={"decisions": decisions, "agent_result": _compact_event_payload(agent_result)},
        )
        failed = str(agent_result.get("opencode_status") or "").lower() == "failed" or bool(agent_result.get("error"))
        return {
            "finding_id": finding_id,
            "status": "failed" if failed else "completed",
            "agent_run_id": agent_run_id or None,
            "decisions": decisions,
            "agent_result": _compact_event_payload(agent_result),
        }
    except Exception as exc:
        result = {"finding_id": finding_id, "status": "failed", "error": str(exc)}
        await _record_pipeline_event(audit_run_id, "judger_finding_failed", result)
        return result


async def _complete_judgement_internal(audit_run_id: str, agent_results: list[dict[str, Any]]) -> dict[str, Any]:
    parsed_decisions: list[dict[str, Any]] = []
    for result in agent_results:
        parsed_decisions.extend([item for item in result.get("decisions", []) if isinstance(item, dict)])
    decisions = await _apply_judgement(audit_run_id, parsed_decisions)
    result = {"audit_run_id": audit_run_id, "agent_runs": agent_results, "decisions": decisions}
    await _record_pipeline_event(audit_run_id, "judgement_completed", result)
    return result


async def _run_source_sink_analysis(
    audit_run_id: str,
    project_id: str,
    workspace_path: str,
    runtime: Any,
    audit_run: dict[str, Any],
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    findings = findings if findings is not None else await _list_findings(audit_run_id)
    if not findings:
        result = {"ok": True, "available": True, "scheduled": 0, "completed": 0, "failed": 0, "skipped": True}
        await _record_pipeline_event(audit_run_id, "source_sink_analysis_skipped", result)
        return result
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    max_parallel = max(1, int(config.get("max_parallel_source_sink_finders") or config.get("max_parallel_code_auditors") or 2))
    max_findings = max(1, int(config.get("max_source_sink_findings") or 50))
    selected = (await _filter_deep_dive_findings(audit_run_id, findings))[:max_findings]
    if not selected:
        result = {
            "ok": True,
            "available": True,
            "scheduled": 0,
            "completed": 0,
            "failed": 0,
            "skipped": True,
            "reason": "no findings with main-agent deep_dive triage decision",
        }
        await _record_pipeline_event(audit_run_id, "source_sink_analysis_skipped", result)
        return result
    semaphore = asyncio.Semaphore(max_parallel)

    async def run_one(finding: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await _run_source_sink_finding_internal(audit_run_id, project_id, workspace_path, runtime, audit_run, finding)

    results = await asyncio.gather(*(run_one(finding) for finding in selected))
    return await _complete_source_sink_analysis_internal(audit_run_id, results)


async def _run_source_sink_finding_internal(
    audit_run_id: str,
    project_id: str,
    workspace_path: str,
    runtime: Any,
    audit_run: dict[str, Any],
    finding: dict[str, Any],
) -> dict[str, Any]:
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    evidence = await _list_evidence(audit_run_id)
    attempts = await _list_validation_attempts(audit_run_id)
    finding_id = str(finding.get("finding_id") or "")
    _ensure_finding_state_markdown(
        audit_run_id,
        finding,
        evidence=[item for item in evidence if str(item.get("finding_id")) == finding_id],
        attempts=[item for item in attempts if str(item.get("finding_id")) == finding_id],
    )
    input_payload = {
        "goal": "For this single Finding, build or reject a source-to-sink attack chain. Return strict JSON with chains[].",
        "audit_phase": "source-sink-analysis",
        "finding": finding,
        "finding_artifact_contract": _finding_artifact_contract(audit_run_id, finding_id, "source-sink"),
        "evidence": [item for item in evidence if str(item.get("finding_id")) == finding_id],
        "validation_attempts": [item for item in attempts if str(item.get("finding_id")) == finding_id],
        "codebase_memory": _codebase_memory_context(),
        "output_contract": {
            "chains": [
                {
                    "finding_id": finding_id,
                    "status": "chain_found|partial|not_found",
                    "source": {"file_path": "...", "line_start": 1, "symbol": "...", "description": "..."},
                    "sink": {"file_path": finding.get("file_path"), "line_start": finding.get("line_start"), "symbol": "...", "description": "..."},
                    "steps": [],
                    "sanitizers": [],
                    "exploitability": "...",
                    "confidence": "high|medium|low",
                    "codebase_memory_queries": [],
                }
            ]
        },
    }
    try:
        agent_result = await runtime.start_agent_run(
            audit_run_id=audit_run_id,
            project_id=project_id,
            agent_name=str(config.get("source_sink_finder_agent_name") or "kimi-source-sink-finder"),
            workspace_host_path=workspace_path,
            allow_external_network=_effective_agent_external_network(audit_run, get_settings()),
            retain_runtime_on_failure=bool(audit_run.get("retain_runtime_on_failure")),
            input_payload=input_payload,
        )
        agent_run_id = str(agent_result.get("agent_run_id") or agent_result.get("run_id") or "")
        chains = await _extract_agent_structured_list(agent_run_id, "chains")
        created = await _persist_source_sink_chains(
            audit_run_id=audit_run_id,
            finding_id=finding_id,
            agent_run_id=agent_run_id or None,
            chains=chains,
        )
        failed = str(agent_result.get("opencode_status") or "").lower() == "failed" or bool(agent_result.get("error"))
        status = "failed" if failed else "completed"
        result = {
            "finding_id": finding_id,
            "status": status,
            "agent_run_id": agent_run_id or None,
            "chains_created": created,
            "agent_result": _compact_event_payload(agent_result),
        }
    except Exception as exc:
        result = {"finding_id": finding_id, "status": "failed", "error": str(exc)}
    await _record_pipeline_event(audit_run_id, "source_sink_finding_completed", result)
    return result


async def _complete_source_sink_analysis_internal(audit_run_id: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = _count_by(results, "status")
    completed = int(status_counts.get("completed") or 0)
    failed = int(status_counts.get("failed") or 0)
    final = {
        "ok": failed == 0,
        "available": True,
        "scheduled": len(results),
        "completed": completed,
        "failed": failed,
        "skipped": 0,
        "status_counts": status_counts,
        "chains_created": sum(int(item.get("chains_created") or 0) for item in results),
        "results": results,
    }
    await _record_pipeline_event(audit_run_id, "source_sink_analysis_completed", final)
    return final


async def _run_whiteboard_swarm(
    audit_run_id: str,
    runtime: Any,
    *,
    override_rounds: int | None = None,
    override_max_tasks_per_round: int | None = None,
) -> dict[str, Any]:
    audit_run = await _get_audit_run(audit_run_id)
    if not audit_run:
        raise LookupError("audit run not found")
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    if not bool(config.get("enable_whiteboard", True)):
        result = {"ok": True, "skipped": True, "reason": "whiteboard disabled"}
        await _record_pipeline_event(audit_run_id, "whiteboard_swarm_skipped", result)
        return result
    if not bool(config.get("enable_whiteboard_swarm", True)):
        result = {"ok": True, "skipped": True, "reason": "whiteboard swarm disabled"}
        await _record_pipeline_event(audit_run_id, "whiteboard_swarm_skipped", result)
        return result
    workspace_path = config.get("workspace_host_path")
    if not workspace_path:
        result = {"ok": False, "error": "audit run has no workspace path"}
        await _record_pipeline_event(audit_run_id, "whiteboard_swarm_failed", result)
        return result
    if runtime is None:
        result = {"ok": False, "error": "runtime is unavailable"}
        await _record_pipeline_event(audit_run_id, "whiteboard_swarm_failed", result)
        return result

    triage = await _triage_whiteboard_swarm_candidates(audit_run_id)
    rounds = max(1, int(override_rounds or config.get("max_whiteboard_rounds") or 3))
    max_tasks_per_round = max(1, int(override_max_tasks_per_round or config.get("max_whiteboard_tasks_per_round") or 8))
    controller_agent = str(config.get("whiteboard_swarm_agent_name") or config.get("agent_name") or "opencode-orchestrator")
    settings = get_settings()
    async with SessionLocal() as session:
        service = WhiteboardService(runtime_settings, session)
        task = WhiteboardTask(
            task_id=str(uuid.uuid4()),
            audit_run_id=audit_run_id,
            project_id=audit_run["project_id"],
            gap_card_id=None,
            agent_role="whiteboard-controller",
            agent_name=controller_agent,
            status="running",
            round_index=1,
            attempt_index=1,
            prompt="AI-controlled whiteboard swarm controller",
            result={},
        )
        session.add(task)
        await session.commit()
        await service.write_snapshot(audit_run_id)

    await _record_pipeline_event(
        audit_run_id,
        "whiteboard_swarm_started",
        {
            "mode": "ai-controller",
            "controller_agent": controller_agent,
            "rounds": rounds,
            "max_tasks_per_round": max_tasks_per_round,
            "triage": triage.get("summary"),
        },
    )
    try:
        graph = await _whiteboard_graph(audit_run_id)
        agent_result = await runtime.start_agent_run(
            audit_run_id=audit_run_id,
            project_id=audit_run["project_id"],
            agent_name=controller_agent,
            workspace_host_path=workspace_path,
            allow_external_network=_effective_agent_external_network(audit_run, get_settings()),
            retain_runtime_on_failure=bool(audit_run.get("retain_runtime_on_failure")),
                input_payload={
                    "goal": (
                        "Act as the Whiteboard swarm controller. Inspect the shared Whiteboard, decide which gaps or partial chains "
                    "deserve more work, and use whiteboard-mcp schedule_agent to launch specialized Agents only for pre-triaged "
                    "high-value candidates. Respect the supplied budgets. Add cards/edges/notes for your reasoning and submit "
                    "chain evidence only when complete."
                    ),
                    "long_running": controller_long_running,
                    "agent_lifecycle": "long-running" if controller_long_running else "prompt",
                    "audit_phase": "whiteboard-swarm-controller",
                "whiteboard_swarm": {
                    "mode": "ai-controller",
                    "controller_task_id": task.task_id,
                    "max_rounds": rounds,
                    "max_agent_schedules": max_tasks_per_round,
                    "candidate_value_triage": triage,
                    "allowed_agent_names": [
                        "kimi-source-sink-finder",
                        "kimi-validator",
                        "opencode-judger",
                        "opencode-poc-writer",
                        "opencode-poc-verifier",
                        "opencode-code-auditor",
                    ],
                    "instruction": (
                        "You decide the next Agent work, but you must only schedule work for card IDs listed in "
                        "candidate_value_triage.eligible_card_ids. Treat candidate_value_triage.excluded_card_ids as appendix-only "
                        "unless you can explicitly connect one to an eligible attack chain. Do not schedule standalone SSL/TLS "
                        "verification, weak password hashing, default credentials, cookie flags, CSRF, debug-mode, or generic "
                        "secret-storage hygiene findings. Use list_graph to inspect all cards, "
                        "search_cards or find_attach_points to locate related cards by keyword or filters, then use "
                        "create_card, link_cards, declare_gap, schedule_agent, and submit_chain_evidence. Card predecessor/successor "
                        "slots must use card_ids arrays, status values not_ready/finding/not_found/hint/impossible, and agent_run_id."
                    ),
                },
                "whiteboard_snapshot": _compact_event_payload(graph),
                "codebase_memory": _codebase_memory_context(),
            },
        )
        agent_run_id = str(agent_result.get("agent_run_id") or agent_result.get("run_id") or "")
        failed = str(agent_result.get("opencode_status") or "").lower() == "failed" or bool(agent_result.get("error"))
        status = "failed" if failed else "completed"
        async with SessionLocal() as session:
            row = await session.scalar(select(WhiteboardTask).where(WhiteboardTask.task_id == task.task_id))
            if row:
                row.status = status
                row.agent_run_id = agent_run_id or None
                row.result = _compact_event_payload(agent_result)
                await session.commit()
            await WhiteboardService(runtime_settings, session).write_snapshot(audit_run_id)
        result = {
            "ok": not failed,
            "mode": "ai-controller",
            "controller_task_id": task.task_id,
            "controller_agent_run_id": agent_run_id or None,
            "scheduled": 1,
            "status_counts": {status: 1},
            "result": _compact_event_payload(agent_result),
        }
    except Exception as exc:
        async with SessionLocal() as session:
            row = await session.scalar(select(WhiteboardTask).where(WhiteboardTask.task_id == task.task_id))
            if row:
                row.status = "failed"
                row.result = {"error": str(exc)}
                await session.commit()
        result = {"ok": False, "mode": "ai-controller", "controller_task_id": task.task_id, "scheduled": 1, "status_counts": {"failed": 1}, "error": str(exc)}
    result = {
        **result,
        "budget": {"max_rounds": rounds, "max_agent_schedules": max_tasks_per_round},
    }
    await _record_pipeline_event(audit_run_id, "whiteboard_swarm_completed", result)
    return result


async def _triage_whiteboard_swarm_candidates(audit_run_id: str) -> dict[str, Any]:
    candidate_card_types = {"candidate_vulnerability", "candidate-vulnerability"}
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(WhiteboardCard)
                .where(WhiteboardCard.audit_run_id == audit_run_id)
                .where(WhiteboardCard.card_type.in_(candidate_card_types))
                .order_by(WhiteboardCard.created_at.asc())
            )
        ).scalars().all()
        eligible: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for row in rows:
            decision = _swarm_candidate_value_decision(row)
            metadata = dict(row.metadata_json or {})
            metadata["swarm_triage"] = decision
            row.metadata_json = metadata
            existing_decision = await session.scalar(
                select(FindingTriageDecision).where(
                    FindingTriageDecision.audit_run_id == audit_run_id,
                    FindingTriageDecision.card_id == row.card_id,
                )
            )
            decision_status = str(decision["decision"])
            deep_dive_allowed = decision_status == "deep_dive"
            poc_allowed = deep_dive_allowed and bool(decision.get("poc_allowed", True))
            values = {
                "project_id": row.project_id,
                "finding_id": row.finding_id,
                "agent_run_id": row.agent_run_id,
                "decision_status": decision_status,
                "decision_reason": "; ".join(decision.get("reasons") or [])[:10000],
                "deep_dive_allowed": deep_dive_allowed,
                "poc_allowed": poc_allowed,
                "confidence": decision.get("confidence") or "medium",
                "signals": decision,
            }
            if existing_decision:
                for key, value in values.items():
                    setattr(existing_decision, key, value)
            else:
                session.add(
                    FindingTriageDecision(
                        decision_id=str(uuid.uuid4()),
                        audit_run_id=audit_run_id,
                        card_id=row.card_id,
                        **values,
                    )
                )
            if decision["decision"] == "deep_dive":
                eligible.append(_triage_card_summary(row, decision))
            else:
                excluded.append(_triage_card_summary(row, decision))
        if rows:
            session.add(
                AuditRunEvent(
                    audit_run_id=audit_run_id,
                    event_type="whiteboard_swarm_candidates_triaged",
                    payload={
                        "candidate_cards": len(rows),
                        "eligible": len(eligible),
                        "excluded": len(excluded),
                        "eligible_card_ids": [item["card_id"] for item in eligible],
                        "excluded_card_ids": [item["card_id"] for item in excluded],
                    },
                )
            )
        await session.commit()
    return {
        "policy": (
            "Swarm should spend agent work only on findings with realistic exploitability and direct impact. "
            "Standalone hygiene findings are appendix-only unless connected to an attack chain."
        ),
        "eligible_card_ids": [item["card_id"] for item in eligible],
        "excluded_card_ids": [item["card_id"] for item in excluded],
        "eligible": eligible[:80],
        "excluded": excluded[:80],
        "summary": {"candidate_cards": len(rows), "eligible": len(eligible), "excluded": len(excluded)},
    }


def _triage_card_summary(card: WhiteboardCard, decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_id": card.card_id,
        "title": card.title,
        "file_path": card.file_path,
        "line_start": card.line_start,
        "decision": decision["decision"],
        "score": decision["score"],
        "reasons": decision["reasons"],
    }


def _swarm_candidate_value_decision(card: WhiteboardCard) -> dict[str, Any]:
    text = " ".join(
        str(item or "")
        for item in [
            card.title,
            card.content,
            card.file_path,
            (card.metadata_json or {}).get("category"),
            (card.metadata_json or {}).get("impact"),
        ]
    ).lower()
    score = 0
    reasons: list[str] = []

    def add(pattern: str, points: int, reason: str) -> None:
        nonlocal score
        if pattern in text:
            score += points
            reasons.append(reason)

    high_value = [
        ("auth bypass", 45, "authentication bypass"),
        ("authentication bypass", 45, "authentication bypass"),
        ("rbac bypass", 40, "authorization bypass"),
        ("idor", 40, "direct object authorization impact"),
        ("ownership", 25, "resource ownership impact"),
        ("missing authorization", 35, "authorization impact"),
        ("sql injection", 45, "database injection"),
        ("raw sql", 25, "raw SQL sink"),
        ("arbitrary file write", 45, "file write primitive"),
        ("file upload rce", 50, "upload-to-code-execution path"),
        ("webshell", 50, "webshell/code execution path"),
        ("ssrf", 30, "server-side request primitive"),
        ("deserialization", 35, "deserialization primitive"),
        ("unserialize", 35, "PHP unserialize primitive"),
        ("jwt forgery", 40, "token forgery impact"),
        ("jwt secret", 25, "token signing secret impact"),
        ("mass assignment", 35, "state-changing mass assignment"),
        ("remote sql execution", 50, "remote SQL execution path"),
        ("dynamic table", 25, "dynamic database target"),
    ]
    for pattern, points, reason in high_value:
        add(pattern, points, reason)

    low_value = [
        "ssl/tls verification",
        "ssl verification",
        "tls verification",
        "weak password",
        "double md5",
        "md5",
        "cookie security",
        "httponly",
        "samesite",
        "csrf",
        "debug mode",
        "default database credentials",
        "hardcoded default",
        "rate limiting",
    ]
    low_hits = [item for item in low_value if item in text]
    if low_hits:
        score -= 40
        reasons.append("standalone hygiene finding: " + ", ".join(low_hits[:3]))

    metadata = card.metadata_json or {}
    severity = str(metadata.get("severity") or metadata.get("risk") or "").lower()
    if severity in {"critical", "high"}:
        score += 15
    elif severity == "medium":
        score += 5

    attack_chain_terms = [
        "attack chain",
        "privilege escalation",
        "account takeover",
        "auth bypass",
        "rce",
        "remote code execution",
        "data exfiltration",
        "source-sink",
    ]
    if low_hits and any(term in text for term in attack_chain_terms):
        score += 50
        reasons.append("low-value smell is connected to an explicit attack-chain claim")

    if score >= 55:
        decision = "deep_dive"
    elif score >= 30:
        decision = "evidence_only"
    elif low_hits:
        decision = "appendix_only"
    else:
        decision = "needs_human"
    return {
        "decision": decision,
        "score": score,
        "reasons": reasons or ["no strong exploitability signal"],
        "deep_dive_allowed": decision == "deep_dive",
        "poc_allowed": decision == "deep_dive",
        "confidence": "high" if abs(score) >= 40 else "medium",
    }


async def _whiteboard_graph(audit_run_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        return await WhiteboardService(get_settings(), session).graph(audit_run_id)


async def _execution_graph(audit_run: dict[str, Any]) -> dict[str, Any]:
    audit_run_id = str(audit_run["audit_run_id"])
    project_id = str(audit_run["project_id"])
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(node: dict[str, Any]) -> None:
        node_id = str(node["id"])
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        nodes.append(node)

    def add_edge(source: str, target: str, edge_type: str, **metadata: Any) -> None:
        key = (source, target, edge_type)
        if source not in seen_nodes or target not in seen_nodes or key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": source, "target": target, "type": edge_type, **metadata})

    add_node(
        {
            "id": f"audit:{audit_run_id}",
            "kind": "audit-run",
            "label": audit_run_id,
            "status": audit_run.get("status"),
            "group": "audit",
            "target": {"view": "audit-runs", "audit_run_id": audit_run_id},
            "data": audit_run,
        }
    )

    events = await _list_audit_run_events(audit_run_id, limit=500)
    step_nodes: dict[str, str] = {}
    step_order: list[str] = []
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        step = str(payload.get("step") or payload.get("stage") or "").strip()
        if not step:
            continue
        step_id = f"step:{step}"
        status = _event_step_status(str(event.get("event_type") or ""))
        if step_id not in step_nodes:
            step_nodes[step] = step_id
            step_order.append(step)
            add_node(
                {
                    "id": step_id,
                    "kind": "pipeline-step",
                    "label": step,
                    "status": status,
                    "group": "pipeline",
                    "target": {"view": "audit-runs", "audit_run_id": audit_run_id},
                    "data": {"latest_event": event},
                }
            )
            add_edge(f"audit:{audit_run_id}", step_id, "contains")
        else:
            for node in nodes:
                if node["id"] == step_id and status != "unknown":
                    node["status"] = status
                    node["data"] = {"latest_event": event}
                    break
    for previous, current in zip(step_order, step_order[1:]):
        add_edge(step_nodes[previous], step_nodes[current], "next")

    async with SessionLocal() as session:
        agent_rows = list(
            (
                await session.execute(
                    select(AgentRun).where(AgentRun.audit_run_id == audit_run_id).order_by(AgentRun.created_at.asc())
                )
            ).scalars()
        )
        container_rows = list(
            (
                await session.execute(
                    select(ContainerRun).where(ContainerRun.audit_run_id == audit_run_id).order_by(ContainerRun.created_at.asc())
                )
            ).scalars()
        )
        task_rows = list(
            (
                await session.execute(
                    select(WhiteboardTask).where(WhiteboardTask.audit_run_id == audit_run_id).order_by(WhiteboardTask.created_at.asc())
                )
            ).scalars()
        )
        card_rows = list(
            (
                await session.execute(
                    select(WhiteboardCard).where(WhiteboardCard.audit_run_id == audit_run_id).order_by(WhiteboardCard.created_at.asc())
                )
            ).scalars()
        )
        whiteboard_edges = list(
            (
                await session.execute(
                    select(WhiteboardEdge).where(WhiteboardEdge.audit_run_id == audit_run_id).order_by(WhiteboardEdge.created_at.asc())
                )
            ).scalars()
        )

    for agent in agent_rows:
        node_id = f"agent:{agent.agent_run_id}"
        output_summary = agent.output_summary or {}
        runtime_name = output_summary.get("acp_runtime") or (output_summary.get("acp_result") or {}).get("runtime_name")
        add_node(
            {
                "id": node_id,
                "kind": "agent-run",
                "label": agent.agent_name,
                "status": agent.status,
                "group": str(runtime_name or _agent_group(agent.agent_name)),
                "target": {"view": "agent-runs", "audit_run_id": audit_run_id, "agent_run_id": agent.agent_run_id},
                "data": _agent_run_to_dict(agent),
            }
        )
        step_id = _agent_step_node_id(agent.agent_name, step_nodes)
        add_edge(step_id or f"audit:{audit_run_id}", node_id, "runs")

    for task in task_rows:
        node_id = f"whiteboard-task:{task.task_id}"
        add_node(
            {
                "id": node_id,
                "kind": "whiteboard-task",
                "label": task.agent_role,
                "status": task.status,
                "group": "whiteboard",
                "target": {"view": "whiteboard", "audit_run_id": audit_run_id, "task_id": task.task_id},
                "data": _whiteboard_task_to_dict(task),
            }
        )
        swarm_step_id = step_nodes.get("whiteboard-swarm") or f"audit:{audit_run_id}"
        add_edge(swarm_step_id, node_id, "schedules")
        if task.agent_run_id:
            add_edge(node_id, f"agent:{task.agent_run_id}", "started")

    for container in container_rows:
        node_id = f"container:{container.container_id}"
        add_node(
            {
                "id": node_id,
                "kind": "container",
                "label": container.container_name or container.container_id[:12],
                "status": container.status,
                "group": container.role,
                "target": {"view": "runtime-containers", "audit_run_id": audit_run_id, "container_id": container.container_id},
                "data": {
                    "container_id": container.container_id,
                    "container_name": container.container_name,
                    "agent_run_id": container.agent_run_id,
                    "image": container.image,
                    "role": container.role,
                    "status": container.status,
                    "exit_code": container.exit_code,
                    "log_artifact": container.log_artifact,
                },
            }
        )
        source = f"agent:{container.agent_run_id}" if container.agent_run_id else f"audit:{audit_run_id}"
        add_edge(source, node_id, "container")

    for card in card_rows:
        node_id = f"whiteboard-card:{card.card_id}"
        add_node(
            {
                "id": node_id,
                "kind": "whiteboard-card",
                "label": card.title,
                "status": card.status,
                "group": card.card_type,
                "target": {"view": "whiteboard", "audit_run_id": audit_run_id, "card_id": card.card_id},
                "data": _whiteboard_card_to_dict(card),
            }
        )
        if card.agent_run_id:
            add_edge(f"agent:{card.agent_run_id}", node_id, "writes")
        elif card.card_type == "gap":
            add_edge(step_nodes.get("whiteboard-swarm") or f"audit:{audit_run_id}", node_id, "tracks")

    for edge in whiteboard_edges:
        source = f"whiteboard-card:{edge.source_card_id}"
        target = f"whiteboard-card:{edge.target_card_id}"
        add_edge(source, target, f"whiteboard:{edge.edge_type}", data=_whiteboard_edge_to_dict(edge))

    return {
        "audit_run_id": audit_run_id,
        "project_id": project_id,
        "summary": _execution_graph_summary(nodes),
        "nodes": nodes,
        "edges": edges,
    }


def _event_step_status(event_type: str) -> str:
    if event_type.endswith("_completed"):
        return "completed"
    if event_type.endswith("_skipped"):
        return "skipped"
    if event_type.endswith("_failed"):
        return "failed"
    if event_type.endswith("_started"):
        return "running"
    return "unknown"


def _agent_group(agent_name: str) -> str:
    return agent_name.split("-", 1)[0] if "-" in agent_name else "agent"


def _agent_step_node_id(agent_name: str, step_nodes: dict[str, str]) -> str | None:
    normalized = agent_name.lower()
    mapping = [
        ("code-auditor", "code-analysis"),
        ("validator", "validation-judgement"),
        ("judger", "validation-judgement"),
        ("poc-writer", "poc-writing"),
        ("poc-verifier", "poc-verification"),
        ("orchestrator", "agent-audit"),
    ]
    for needle, step in mapping:
        if needle in normalized and step in step_nodes:
            return step_nodes[step]
    return None


def _execution_graph_summary(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for node in nodes:
        kind = str(node.get("kind") or "unknown")
        status = str(node.get("status") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
    unfinished_statuses = {"created", "starting", "queued", "running", "open", "needs_agent", "agent_queued"}
    return {
        "node_count": len(nodes),
        "by_kind": by_kind,
        "by_status": by_status,
        "completed": sum(count for status, count in by_status.items() if status in {"completed", "confirmed", "closed"}),
        "unfinished": sum(count for status, count in by_status.items() if status in unfinished_statuses),
        "failed": sum(count for status, count in by_status.items() if status in {"failed", "cancelled"}),
    }


async def _generate_pocs_internal(audit_run_id: str, runtime: Any) -> dict[str, Any]:
    audit_run = await _get_audit_run(audit_run_id)
    if not audit_run:
        return {"missing": True}
    workspace_path = audit_run.get("config", {}).get("workspace_host_path")
    if not workspace_path:
        return {"ok": False, "error": "audit run has no workspace path"}
    findings = await _list_findings(audit_run_id)
    selected = await _filter_poc_allowed_findings(audit_run_id, _poc_candidate_findings(findings))
    if not selected:
        result = {"ok": True, "scheduled": 0, "completed": 0, "failed": 0, "skipped": True, "reason": "no confirmed findings"}
        await _record_pipeline_event(audit_run_id, "poc_writing_skipped", result)
        return result
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    max_parallel = max(1, int(config.get("max_parallel_poc_writers") or 2))
    max_findings = max(1, int(config.get("max_poc_findings") or 25))
    selected = selected[:max_findings]
    semaphore = asyncio.Semaphore(max_parallel)

    async def run_one(finding: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await _run_poc_writer_finding_internal(audit_run_id, runtime, audit_run, finding)

    results = await asyncio.gather(*(run_one(finding) for finding in selected))
    return await _complete_poc_writing_internal(audit_run_id, results)


async def _run_poc_writer_finding_internal(audit_run_id: str, runtime: Any, audit_run: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any]:
    workspace_path = audit_run.get("config", {}).get("workspace_host_path")
    if not workspace_path:
        return {"finding_id": str(finding.get("finding_id") or ""), "status": "failed", "error": "audit run has no workspace path"}
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    evidence = await _list_evidence(audit_run_id)
    attempts = await _list_validation_attempts(audit_run_id)
    finding_id = str(finding.get("finding_id") or "")
    _ensure_finding_state_markdown(
        audit_run_id,
        finding,
        evidence=[item for item in evidence if str(item.get("finding_id")) == finding_id],
        attempts=[item for item in attempts if str(item.get("finding_id")) == finding_id],
    )
    input_payload = {
        "goal": "Write a reproducible proof of concept for this single confirmed Finding. Return strict JSON with pocs[].",
        "audit_phase": "poc-writing",
        "finding": finding,
        "finding_artifact_contract": _finding_artifact_contract(audit_run_id, finding_id, "poc-writer"),
        "evidence": [item for item in evidence if str(item.get("finding_id")) == finding_id],
        "validation_attempts": [item for item in attempts if str(item.get("finding_id")) == finding_id],
        "codebase_memory": _codebase_memory_context(),
    }
    try:
        agent_result = await runtime.start_agent_run(
            audit_run_id=audit_run_id,
            project_id=audit_run["project_id"],
            agent_name=str(config.get("poc_writer_agent_name") or "opencode-poc-writer"),
            workspace_host_path=workspace_path,
            allow_external_network=_effective_agent_external_network(audit_run, get_settings()),
            retain_runtime_on_failure=bool(audit_run.get("retain_runtime_on_failure")),
            input_payload=input_payload,
        )
        agent_run_id = str(agent_result.get("agent_run_id") or agent_result.get("run_id") or "")
        pocs = await _extract_agent_structured_list(agent_run_id, "pocs")
        artifacts = await _persist_poc_artifacts(
            audit_run=audit_run,
            finding=finding,
            agent_run_id=agent_run_id or None,
            pocs=pocs,
        )
        failed = str(agent_result.get("opencode_status") or "").lower() == "failed" or bool(agent_result.get("error"))
        status = "failed" if failed else "completed"
        result = {
            "finding_id": finding_id,
            "status": status,
            "agent_run_id": agent_run_id or None,
            "poc_artifacts": artifacts,
            "agent_result": _compact_event_payload(agent_result),
        }
    except Exception as exc:
        result = {"finding_id": finding_id, "status": "failed", "error": str(exc)}
    await _record_pipeline_event(audit_run_id, "poc_finding_completed", result)
    return result


async def _complete_poc_writing_internal(audit_run_id: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = _count_by(results, "status")
    failed = int(status_counts.get("failed") or 0)
    final = {
        "ok": failed == 0,
        "scheduled": len(results),
        "completed": int(status_counts.get("completed") or 0),
        "failed": failed,
        "status_counts": status_counts,
        "poc_artifact_count": sum(len(item.get("poc_artifacts") or []) for item in results),
        "results": results,
    }
    await _record_pipeline_event(audit_run_id, "poc_writing_completed", final)
    return final


async def _verify_pocs_internal(audit_run_id: str, runtime: Any) -> dict[str, Any]:
    audit_run = await _get_audit_run(audit_run_id)
    if not audit_run:
        return {"missing": True}
    workspace_path = audit_run.get("config", {}).get("workspace_host_path")
    findings = await _list_findings(audit_run_id)
    evidence = await _list_evidence(audit_run_id)
    poc_evidence = [item for item in evidence if str(item.get("kind") or "") in {"poc-artifact", "poc-plan"}]
    if not workspace_path or not poc_evidence:
        result = {
            "ok": True,
            "scheduled": 0,
            "completed": 0,
            "failed": 0,
            "skipped": True,
            "reason": "no PoC artifacts or workspace unavailable",
        }
        await _record_pipeline_event(audit_run_id, "poc_verification_skipped", result)
        return result
    findings_by_id = {str(item.get("finding_id")): item for item in findings}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in poc_evidence:
        grouped.setdefault(str(item.get("finding_id") or ""), []).append(item)
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    max_parallel = max(1, int(config.get("max_parallel_poc_verifiers") or 2))
    semaphore = asyncio.Semaphore(max_parallel)

    async def run_one(finding_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        finding = findings_by_id.get(finding_id)
        if not finding:
            return {"finding_id": finding_id, "status": "skipped", "reason": "finding not found"}
        async with semaphore:
            return await _run_poc_verifier_finding_internal(audit_run_id, runtime, audit_run, finding, items)

    results = await asyncio.gather(*(run_one(finding_id, items) for finding_id, items in grouped.items()))
    return await _complete_poc_verification_internal(audit_run_id, results)


async def _run_poc_verifier_finding_internal(
    audit_run_id: str,
    runtime: Any,
    audit_run: dict[str, Any],
    finding: dict[str, Any],
    poc_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    workspace_path = audit_run.get("config", {}).get("workspace_host_path")
    if not workspace_path:
        return {"finding_id": str(finding.get("finding_id") or ""), "status": "failed", "error": "audit run has no workspace path"}
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    finding_id = str(finding.get("finding_id") or "")
    evidence = await _list_evidence(audit_run_id)
    _ensure_finding_state_markdown(
        audit_run_id,
        finding,
        evidence=[item for item in evidence if str(item.get("finding_id")) == finding_id],
        attempts=[],
    )
    input_payload = {
        "goal": "Verify the generated PoC for this single Finding. Return strict JSON with verifications[].",
        "audit_phase": "poc-verification",
        "finding": finding,
        "finding_artifact_contract": _finding_artifact_contract(audit_run_id, finding_id, "poc-verifier"),
        "poc_evidence": poc_evidence,
        "source_sink_evidence": [item for item in evidence if item.get("finding_id") == finding_id and item.get("kind") == "source-sink-chain"],
        "codebase_memory": _codebase_memory_context(),
    }
    try:
        agent_result = await runtime.start_agent_run(
            audit_run_id=audit_run_id,
            project_id=audit_run["project_id"],
            agent_name=str(config.get("poc_verifier_agent_name") or "opencode-poc-verifier"),
            workspace_host_path=workspace_path,
            allow_external_network=_effective_agent_external_network(audit_run, get_settings()),
            retain_runtime_on_failure=bool(audit_run.get("retain_runtime_on_failure")),
            input_payload=input_payload,
        )
        agent_run_id = str(agent_result.get("agent_run_id") or agent_result.get("run_id") or "")
        verifications = await _extract_agent_structured_list(agent_run_id, "verifications")
        created = await _persist_poc_verifications(
            audit_run_id=audit_run_id,
            finding_id=finding_id,
            agent_run_id=agent_run_id or None,
            verifications=verifications,
        )
        failed = str(agent_result.get("opencode_status") or "").lower() == "failed" or bool(agent_result.get("error"))
        status = "failed" if failed else "completed"
        result = {
            "finding_id": finding_id,
            "status": status,
            "agent_run_id": agent_run_id or None,
            "verification_evidence_created": created,
            "agent_result": _compact_event_payload(agent_result),
        }
    except Exception as exc:
        result = {"finding_id": finding_id, "status": "failed", "error": str(exc)}
    await _record_pipeline_event(audit_run_id, "poc_verification_finding_completed", result)
    return result


async def _complete_poc_verification_internal(audit_run_id: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = _count_by(results, "status")
    failed = int(status_counts.get("failed") or 0)
    final = {
        "ok": failed == 0,
        "scheduled": len(results),
        "completed": int(status_counts.get("completed") or 0),
        "failed": failed,
        "status_counts": status_counts,
        "verification_evidence_created": sum(int(item.get("verification_evidence_created") or 0) for item in results),
        "results": results,
    }
    await _record_pipeline_event(audit_run_id, "poc_verification_completed", final)
    return final


async def _generate_report_internal(audit_run_id: str, settings: Settings) -> dict[str, Any]:
    audit_run = await _get_audit_run(audit_run_id)
    if not audit_run:
        return {"missing": True}
    findings = await _list_findings(audit_run_id)
    evidence = await _list_evidence(audit_run_id)
    attempts = await _list_validation_attempts(audit_run_id)
    agent_runs = await _list_agent_runs(audit_run_id)
    audit_events = await _list_audit_run_events(audit_run_id)
    dependencies = await _list_dependency_records(audit_run_id)
    summary = _report_summary(
        findings=findings,
        evidence=evidence,
        attempts=attempts,
        agent_runs=agent_runs,
        audit_events=audit_events,
        dependencies=dependencies,
    )
    payload = {
        "audit_run": audit_run,
        "summary": summary,
        "findings": findings,
        "evidence": evidence,
        "validation_attempts": attempts,
        "agent_runs": agent_runs,
        "audit_events": audit_events,
        "dependencies": dependencies,
    }
    finding_reports = await _generate_finding_reports(
        settings=settings,
        audit_run=audit_run,
        findings=findings,
        evidence=evidence,
        attempts=attempts,
        agent_runs=agent_runs,
        audit_events=audit_events,
    )
    summary = {**summary, "finding_report_count": len(finding_reports), "finding_reports": finding_reports}
    payload["summary"] = summary
    payload["finding_reports"] = finding_reports
    report_id = str(uuid.uuid4())
    store = ArtifactStore(settings)
    markdown_metadata = store.put_text(
        f"reports/{audit_run_id}/{report_id}.md",
        _report_markdown(payload),
        content_type="text/markdown; charset=utf-8",
    )
    json_payload = _report_json_index_payload(
        audit_run=audit_run,
        summary=summary,
        findings=findings,
        finding_reports=finding_reports,
    )
    json_metadata = store.put_json(f"reports/{audit_run_id}/{report_id}.json", json_payload)
    summary = {
        **summary,
        "json_path": json_metadata["path"],
        "json_artifact_id": json_metadata["artifact_id"],
        "json_artifact_uri": json_metadata["artifact_uri"],
    }
    markdown_path = markdown_metadata["path"]
    async with SessionLocal() as session:
        session.add(
            ReportArtifact(
                report_id=report_id,
                audit_run_id=audit_run_id,
                project_id=audit_run["project_id"],
                kind="markdown",
                path=markdown_path,
                summary=summary,
            )
        )
        await session.commit()
    report_reference = [
        {
            "kind": "report",
            "project_id": audit_run["project_id"],
            "audit_run_id": audit_run_id,
            "record_id": report_id,
        }
    ]
    json_reference = [
        {
            "kind": "report_json",
            "project_id": audit_run["project_id"],
            "audit_run_id": audit_run_id,
            "record_id": report_id,
        }
    ]
    await _upsert_artifact_record(markdown_metadata, report_reference)
    await _upsert_artifact_record(json_metadata, json_reference)
    result = {
        "report_id": report_id,
        "markdown_path": markdown_metadata["path"],
        "markdown_artifact_id": markdown_metadata["artifact_id"],
        "markdown_artifact_uri": markdown_metadata["artifact_uri"],
        "json_path": json_metadata["path"],
        "json_artifact_id": json_metadata["artifact_id"],
        "json_artifact_uri": json_metadata["artifact_uri"],
        "finding_reports": finding_reports,
        "summary": summary,
    }
    await _record_pipeline_event(audit_run_id, "report_generated", result)
    with contextlib.suppress(Exception):
        result["deliverables"] = await _build_deliverable_package(audit_run_id, settings)
    return result


async def _build_deliverable_package(audit_run_id: str, settings: Settings) -> dict[str, Any]:
    audit_run = await _get_audit_run(audit_run_id)
    if not audit_run:
        return {"missing": True}
    findings = await _list_findings(audit_run_id)
    evidence = await _list_evidence(audit_run_id)
    attempts = await _list_validation_attempts(audit_run_id)
    agent_runs = await _list_agent_runs(audit_run_id)
    triage = await _list_triage_decisions(audit_run_id)
    triage_by_finding = {str(item.get("finding_id") or ""): item for item in triage if item.get("finding_id")}
    deep_dive_findings = [
        finding
        for finding in findings
        if (triage_by_finding.get(str(finding.get("finding_id") or "")) or {}).get("decision_status") == "deep_dive"
    ]
    low_value_findings = [
        finding
        for finding in findings
        if (triage_by_finding.get(str(finding.get("finding_id") or "")) or {}).get("decision_status")
        in {"appendix_only", "evidence_only", "reject", "needs_human"}
    ]
    store = ArtifactStore(settings)
    root = f"deliverables/{audit_run_id}"
    written: list[dict[str, Any]] = []

    def put(kind: str, relative_path: str, text: str, *, finding_id: str | None = None, title: str | None = None) -> dict[str, Any]:
        metadata = store.put_text(relative_path, text, content_type="text/markdown; charset=utf-8")
        written.append({**metadata, "kind": kind, "finding_id": finding_id, "title": title})
        return metadata

    main_metadata = put(
        "main-report",
        f"{root}/main-report.md",
        _deliverable_main_report_markdown(
            audit_run=audit_run,
            findings=deep_dive_findings,
            evidence=evidence,
            attempts=attempts,
            triage_by_finding=triage_by_finding,
        ),
        title="Main Report",
    )
    appendix_metadata = put(
        "low-value-appendix",
        f"{root}/appendix/low-value-evidence.md",
        _deliverable_low_value_appendix_markdown(low_value_findings, triage_by_finding),
        title="Low Value Evidence Appendix",
    )
    for finding in findings:
        finding_id = str(finding.get("finding_id") or "")
        if not finding_id:
            continue
        finding_evidence = [item for item in evidence if str(item.get("finding_id")) == finding_id]
        finding_attempts = [item for item in attempts if str(item.get("finding_id")) == finding_id]
        finding_triage = triage_by_finding.get(finding_id)
        put(
            "finding-report",
            f"{root}/findings/{finding_id}/report.md",
            _deliverable_finding_report_markdown(finding, finding_evidence, finding_attempts, finding_triage),
            finding_id=finding_id,
            title=str(finding.get("title") or finding_id),
        )
        put(
            "finding-evidence",
            f"{root}/findings/{finding_id}/evidence.md",
            _deliverable_finding_evidence_markdown(finding, finding_evidence, finding_attempts),
            finding_id=finding_id,
            title=f"Evidence: {finding.get('title') or finding_id}",
        )
        poc_items = [item for item in finding_evidence if str(item.get("kind") or "").startswith("poc")]
        put(
            "finding-poc-index",
            f"{root}/findings/{finding_id}/poc/README.md",
            _deliverable_poc_index_markdown(finding, poc_items),
            finding_id=finding_id,
            title=f"PoC: {finding.get('title') or finding_id}",
        )
    index_metadata = put(
        "index",
        f"{root}/index.md",
        _deliverable_index_markdown(audit_run, main_metadata, appendix_metadata, written),
        title="Deliverable Index",
    )
    await _upsert_deliverable_artifacts(audit_run, written)
    await _record_pipeline_event(
        audit_run_id,
        "deliverable_package_generated",
        {
            "root": root,
            "artifact_count": len(written),
            "index_path": index_metadata["path"],
            "main_report_path": main_metadata["path"],
        },
    )
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(DeliverableArtifact)
                .where(DeliverableArtifact.audit_run_id == audit_run_id)
                .order_by(DeliverableArtifact.kind.asc(), DeliverableArtifact.created_at.asc())
            )
        ).scalars().all()
    return {"audit_run_id": audit_run_id, "root": root, "artifacts": [_deliverable_artifact_to_dict(row) for row in rows]}


async def _generate_finding_reports(
    *,
    settings: Settings,
    audit_run: dict[str, Any],
    findings: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    agent_runs: list[dict[str, Any]],
    audit_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    store = ArtifactStore(settings)
    reports: list[dict[str, Any]] = []
    audit_run_id = audit_run["audit_run_id"]
    project_id = audit_run["project_id"]
    for finding in findings:
        finding_id = str(finding.get("finding_id") or "")
        if not finding_id:
            continue
        finding_evidence = [item for item in evidence if str(item.get("finding_id")) == finding_id]
        finding_attempts = [item for item in attempts if str(item.get("finding_id")) == finding_id]
        payload = {
            "audit_run": audit_run,
            "finding": finding,
            "finding_markdown": finding.get("finding_markdown") or _finding_markdown_reference(audit_run_id, finding_id),
            "evidence": finding_evidence,
            "validation_attempts": finding_attempts,
            "agent_runs": _agent_runs_for_finding(agent_runs, finding, finding_evidence, finding_attempts),
            "audit_events": _audit_events_for_finding(audit_events, finding_id),
        }
        report_id = str(uuid.uuid4())
        base = f"findings/{audit_run_id}/{finding_id}/reports/{report_id}"
        markdown_metadata = store.put_text(
            f"{base}.md",
            _finding_report_markdown(payload),
            content_type="text/markdown; charset=utf-8",
        )
        json_metadata = store.put_json(f"{base}.json", payload)
        summary = {
            "finding_id": finding_id,
            "title": finding.get("title"),
            "severity": finding.get("severity"),
            "status": finding.get("status"),
            "finding_markdown": payload["finding_markdown"],
            "evidence_count": len(finding_evidence),
            "validation_attempt_count": len(finding_attempts),
            "source_sink_chain_count": sum(1 for item in finding_evidence if item.get("kind") == "source-sink-chain"),
            "poc_artifact_count": sum(1 for item in finding_evidence if item.get("kind") == "poc-artifact"),
            "poc_verification_count": sum(1 for item in finding_evidence if item.get("kind") == "poc-verification"),
            "json_path": json_metadata["path"],
            "json_artifact_id": json_metadata["artifact_id"],
        }
        async with SessionLocal() as session:
            session.add(
                ReportArtifact(
                    report_id=report_id,
                    audit_run_id=audit_run_id,
                    project_id=project_id,
                    kind="finding-markdown",
                    path=markdown_metadata["path"],
                    summary=summary,
                )
            )
            await session.commit()
        reference = {
            "kind": "finding_report",
            "project_id": project_id,
            "audit_run_id": audit_run_id,
            "record_id": finding_id,
            "report_id": report_id,
        }
        await _upsert_artifact_record(markdown_metadata, [reference])
        await _upsert_artifact_record(json_metadata, [{**reference, "kind": "finding_report_json"}])
        reports.append(
            {
                "finding_id": finding_id,
                "report_id": report_id,
                "markdown_path": markdown_metadata["path"],
                "markdown_artifact_id": markdown_metadata["artifact_id"],
                "json_path": json_metadata["path"],
                "json_artifact_id": json_metadata["artifact_id"],
            }
        )
    return reports


async def _list_triage_decisions(audit_run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(FindingTriageDecision)
                .where(FindingTriageDecision.audit_run_id == audit_run_id)
                .order_by(FindingTriageDecision.created_at.asc())
            )
        ).scalars()
        return [_finding_triage_decision_to_dict(row) for row in rows]


async def _upsert_deliverable_artifacts(audit_run: dict[str, Any], artifacts: list[dict[str, Any]]) -> None:
    async with SessionLocal() as session:
        await session.execute(delete(DeliverableArtifact).where(DeliverableArtifact.audit_run_id == audit_run["audit_run_id"]))
        for metadata in artifacts:
            session.add(
                DeliverableArtifact(
                    artifact_id=str(uuid.uuid4()),
                    audit_run_id=audit_run["audit_run_id"],
                    project_id=audit_run["project_id"],
                    finding_id=metadata.get("finding_id"),
                    kind=str(metadata.get("kind") or "artifact"),
                    path=str(metadata["path"]),
                    title=metadata.get("title"),
                    content_type=metadata.get("content_type"),
                    size=int(metadata.get("size") or 0),
                    sha256=metadata.get("sha256"),
                    metadata_json={
                        "artifact_id": metadata.get("artifact_id"),
                        "artifact_uri": metadata.get("artifact_uri"),
                        "relative_path": metadata.get("relative_path"),
                        "download_url": metadata.get("download_url"),
                    },
                )
            )
        await session.commit()
    for metadata in artifacts:
        await _upsert_artifact_record(
            metadata,
            [
                {
                    "kind": "deliverable",
                    "project_id": audit_run["project_id"],
                    "audit_run_id": audit_run["audit_run_id"],
                    "record_id": metadata.get("finding_id") or metadata.get("kind"),
                }
            ],
        )


def _deliverable_index_markdown(
    audit_run: dict[str, Any],
    main_metadata: dict[str, Any],
    appendix_metadata: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> str:
    lines = [
        f"# Audit Deliverable Package: {audit_run['audit_run_id']}",
        "",
        f"- Project ID: `{audit_run.get('project_id')}`",
        f"- Main report: `{main_metadata.get('relative_path')}`",
        f"- Low-value appendix: `{appendix_metadata.get('relative_path')}`",
        f"- Artifact count: `{len(artifacts)}`",
        "",
        "## Contents",
        "",
    ]
    for item in artifacts:
        lines.append(f"- `{item.get('kind')}` `{item.get('relative_path')}`")
    return "\n".join(lines)


def _deliverable_main_report_markdown(
    *,
    audit_run: dict[str, Any],
    findings: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    triage_by_finding: dict[str, dict[str, Any]],
) -> str:
    lines = [
        f"# Audit Report: {audit_run['audit_run_id']}",
        "",
        "## Summary",
        "",
        f"- Deep-dive findings: `{len(findings)}`",
        f"- Evidence records: `{len(evidence)}`",
        f"- Validation attempts: `{len(attempts)}`",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("- No findings were approved for deep dive by main-agent triage.")
    for finding in findings:
        finding_id = str(finding.get("finding_id") or "")
        finding_evidence = [item for item in evidence if str(item.get("finding_id")) == finding_id]
        triage = triage_by_finding.get(finding_id) or {}
        lines.extend(
            [
                f"### {finding.get('title') or finding_id}",
                "",
                f"- Finding ID: `{finding_id}`",
                f"- Severity: `{finding.get('severity') or 'unknown'}`",
                f"- Status: `{finding.get('status') or 'unknown'}`",
                f"- Location: `{finding.get('file_path') or '-'}`:{finding.get('line_start') or '-'}",
                f"- Triage: `{triage.get('decision_status') or '-'}`",
                f"- Evidence count: `{len(finding_evidence)}`",
                "",
                str(finding.get("description") or "-"),
                "",
            ]
        )
    return "\n".join(lines)


def _deliverable_low_value_appendix_markdown(findings: list[dict[str, Any]], triage_by_finding: dict[str, dict[str, Any]]) -> str:
    lines = ["# Low-Value Evidence Appendix", ""]
    if not findings:
        lines.append("- No appendix-only/evidence-only findings recorded.")
        return "\n".join(lines)
    for finding in findings:
        finding_id = str(finding.get("finding_id") or "")
        triage = triage_by_finding.get(finding_id) or {}
        lines.extend(
            [
                f"## {finding.get('title') or finding_id}",
                "",
                f"- Finding ID: `{finding_id}`",
                f"- Decision: `{triage.get('decision_status') or '-'}`",
                f"- Reason: {triage.get('decision_reason') or '-'}",
                f"- Location: `{finding.get('file_path') or '-'}`:{finding.get('line_start') or '-'}",
                "",
            ]
        )
    return "\n".join(lines)


def _deliverable_finding_report_markdown(
    finding: dict[str, Any],
    evidence: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    triage: dict[str, Any] | None,
) -> str:
    finding_id = str(finding.get("finding_id") or "")
    lines = [
        f"# Finding Report: {finding.get('title') or finding_id}",
        "",
        f"- Finding ID: `{finding_id}`",
        f"- Severity: `{finding.get('severity') or 'unknown'}`",
        f"- Status: `{finding.get('status') or 'unknown'}`",
        f"- Triage: `{(triage or {}).get('decision_status') or '-'}`",
        f"- Triage reason: {(triage or {}).get('decision_reason') or '-'}",
        f"- Location: `{finding.get('file_path') or '-'}`:{finding.get('line_start') or '-'}",
        "",
        "## Description",
        "",
        str(finding.get("description") or "-"),
        "",
        "## Evidence Summary",
        "",
    ]
    lines.extend([f"- `{item.get('kind')}` {item.get('summary') or item.get('evidence_id')}" for item in evidence] or ["- None."])
    lines.extend(["", "## Validation", ""])
    lines.extend([f"- Round `{item.get('round_index')}` status `{item.get('status')}`" for item in attempts] or ["- None."])
    return "\n".join(lines)


def _deliverable_finding_evidence_markdown(
    finding: dict[str, Any],
    evidence: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> str:
    lines = [f"# Evidence: {finding.get('title') or finding.get('finding_id')}", ""]
    for item in evidence:
        lines.extend(
            [
                f"## {item.get('kind') or item.get('evidence_id')}",
                "",
                f"- Evidence ID: `{item.get('evidence_id')}`",
                f"- Artifact: `{item.get('artifact_path') or '-'}`",
                "",
                str(item.get("summary") or "-"),
                "",
            ]
        )
    if not evidence:
        lines.append("- No evidence records.")
    if attempts:
        lines.extend(["", "## Validation Logs", ""])
        for item in attempts:
            lines.append(f"- `{item.get('attempt_id')}` round `{item.get('round_index')}` status `{item.get('status')}`")
    return "\n".join(lines)


def _deliverable_poc_index_markdown(finding: dict[str, Any], poc_items: list[dict[str, Any]]) -> str:
    lines = [f"# PoC Index: {finding.get('title') or finding.get('finding_id')}", ""]
    if not poc_items:
        lines.append("- No PoC artifact registered for this finding.")
        return "\n".join(lines)
    for item in poc_items:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        lines.extend(
            [
                f"- `{item.get('kind')}` {item.get('summary') or item.get('evidence_id')}",
                f"  - Artifact: `{item.get('artifact_path') or payload.get('path') or '-'}`",
                f"  - AgentRun: `{payload.get('agent_run_id') or '-'}`",
            ]
        )
    return "\n".join(lines)


async def _extract_agent_structured_list(agent_run_id: str, key: str) -> list[dict[str, Any]]:
    if not agent_run_id:
        return []
    async with SessionLocal() as session:
        agent_run = await session.scalar(select(AgentRun).where(AgentRun.agent_run_id == agent_run_id))
        if not agent_run:
            return []
        payload = agent_run.output_summary or {}
    for candidate in _walk_values(payload):
        parsed = None
        if isinstance(candidate, dict) and key in candidate:
            parsed = candidate
        elif isinstance(candidate, str) and key in candidate:
            parsed = _parse_json_object(candidate)
        if not isinstance(parsed, dict):
            continue
        items = parsed.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


async def _persist_source_sink_chains(
    *,
    audit_run_id: str,
    finding_id: str,
    agent_run_id: str | None,
    chains: list[dict[str, Any]],
) -> int:
    if not chains:
        chains = [{"finding_id": finding_id, "status": "not_found", "notes": "source-sink finder returned no chains"}]
    created = 0
    async with SessionLocal() as session:
        for chain in chains:
            if str(chain.get("finding_id") or finding_id) != finding_id:
                continue
            session.add(
                Evidence(
                    evidence_id=str(uuid.uuid4()),
                    finding_id=finding_id,
                    audit_run_id=audit_run_id,
                    kind="source-sink-chain",
                    summary=str(chain.get("exploitability") or chain.get("summary") or chain.get("status") or "source-to-sink chain"),
                    payload={**chain, "agent_run_id": agent_run_id},
                )
            )
            created += 1
        await session.commit()
    await _write_finding_agent_report(
        audit_run_id=audit_run_id,
        finding_id=finding_id,
        stage="source-sink",
        agent_run_id=agent_run_id,
        title="Source-to-Sink Analysis",
        payload={"chains": chains},
    )
    return created


async def _persist_poc_artifacts(
    *,
    audit_run: dict[str, Any],
    finding: dict[str, Any],
    agent_run_id: str | None,
    pocs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    audit_run_id = audit_run["audit_run_id"]
    finding_id = str(finding.get("finding_id") or "")
    if not pocs:
        markdown = finding.get("finding_markdown") or _finding_markdown_reference(audit_run_id, finding_id)
        poc = {
            "finding_id": finding_id,
            "title": f"Markdown-tracked PoC for {finding.get('title') or finding_id}",
            "language": "manual",
            "artifact_name": "finding-markdown-poc",
            "content": "The PoC Writer produced markdown-first output. Use the linked finding.md and PoC Writer stage report as the authoritative PoC draft.",
            "commands": [],
            "expected_result": "Review the PoC Writer Update section in finding.md and the preserved PoC Writer report.",
            "cleanup_steps": [],
            "safety_notes": "Markdown-first PoC artifact registered by the platform because no structured pocs[] payload was emitted.",
        }
        async with SessionLocal() as session:
            session.add(
                Evidence(
                    evidence_id=str(uuid.uuid4()),
                    finding_id=finding_id,
                    audit_run_id=audit_run_id,
                    kind="poc-artifact",
                    summary="PoC writer output is tracked in finding.md",
                    artifact_path=markdown.get("path"),
                    payload={
                        "poc": poc,
                        "finding_markdown": markdown,
                        "agent_run_id": agent_run_id,
                        "artifact_id": markdown.get("artifact_id"),
                        "artifact_uri": markdown.get("artifact_uri"),
                        "markdown_first": True,
                        "registration_source": "finding_markdown",
                    },
                )
            )
            await session.commit()
        await _write_finding_agent_report(
            audit_run_id=audit_run_id,
            finding_id=finding_id,
            stage="poc-writer",
            agent_run_id=agent_run_id,
            title="PoC Writer Report",
            payload={"pocs": [], "finding_markdown": markdown, "markdown_first": True},
        )
        return [
            {
                "finding_id": finding_id,
                "artifact_id": markdown.get("artifact_id"),
                "artifact_uri": markdown.get("artifact_uri"),
                "path": markdown.get("path"),
                "kind": "poc-artifact",
                "markdown_first": True,
            }
        ]
    store = ArtifactStore(get_settings())
    artifacts: list[dict[str, Any]] = []
    for index, poc in enumerate(pocs):
        if str(poc.get("finding_id") or finding_id) != finding_id:
            continue
        artifact_name = _safe_report_name(str(poc.get("artifact_name") or poc.get("title") or f"poc-{index + 1}"))
        content = _poc_markdown(finding=finding, poc=poc, agent_run_id=agent_run_id)
        metadata = store.put_text(
            f"findings/{audit_run_id}/{finding_id}/poc/{artifact_name}.md",
            content,
            content_type="text/markdown; charset=utf-8",
        )
        json_metadata = store.put_json(
            f"findings/{audit_run_id}/{finding_id}/poc/{artifact_name}.json",
            {"finding": finding, "poc": poc, "agent_run_id": agent_run_id},
        )
        reference = {
            "kind": "finding_poc",
            "project_id": audit_run["project_id"],
            "audit_run_id": audit_run_id,
            "record_id": finding_id,
            "agent_run_id": agent_run_id,
        }
        await _upsert_artifact_record(metadata, [reference])
        await _upsert_artifact_record(json_metadata, [{**reference, "kind": "finding_poc_json"}])
        async with SessionLocal() as session:
            session.add(
                Evidence(
                    evidence_id=str(uuid.uuid4()),
                    finding_id=finding_id,
                    audit_run_id=audit_run_id,
                    kind="poc-artifact",
                    summary=str(poc.get("expected_result") or poc.get("title") or "PoC artifact"),
                    artifact_path=metadata["path"],
                    payload={
                        "poc": poc,
                        "agent_run_id": agent_run_id,
                        "artifact_id": metadata["artifact_id"],
                        "artifact_uri": metadata["artifact_uri"],
                        "json_artifact_id": json_metadata["artifact_id"],
                    },
                )
            )
            await session.commit()
        artifacts.append(
            {
                "finding_id": finding_id,
                "artifact_id": metadata["artifact_id"],
                "artifact_uri": metadata["artifact_uri"],
                "path": metadata["path"],
                "json_artifact_id": json_metadata["artifact_id"],
            }
        )
    await _write_finding_agent_report(
        audit_run_id=audit_run_id,
        finding_id=finding_id,
        stage="poc-writer",
        agent_run_id=agent_run_id,
        title="PoC Writer Report",
        payload={"pocs": pocs, "artifacts": artifacts},
    )
    return artifacts


async def _persist_poc_verifications(
    *,
    audit_run_id: str,
    finding_id: str,
    agent_run_id: str | None,
    verifications: list[dict[str, Any]],
) -> int:
    if not verifications:
        markdown = _finding_markdown_reference(audit_run_id, finding_id)
        verification = {
            "finding_id": finding_id,
            "status": "not_executed",
            "reason": "PoC verifier produced markdown-first output or no structured verifications[] payload. Review finding.md and the PoC Verifier report.",
            "required_changes": [],
            "expected_execution": {},
            "safety_notes": "Registered as platform evidence so the Finding report reflects that verification was attempted.",
            "markdown_first": True,
        }
        async with SessionLocal() as session:
            session.add(
                Evidence(
                    evidence_id=str(uuid.uuid4()),
                    finding_id=finding_id,
                    audit_run_id=audit_run_id,
                    kind="poc-verification",
                    summary="PoC verifier output is tracked in finding.md",
                    artifact_path=markdown.get("path"),
                    payload={
                        **verification,
                        "finding_markdown": markdown,
                        "agent_run_id": agent_run_id,
                        "artifact_id": markdown.get("artifact_id"),
                        "artifact_uri": markdown.get("artifact_uri"),
                        "markdown_first": True,
                        "registration_source": "finding_markdown",
                    },
                )
            )
            await session.commit()
        await _write_finding_agent_report(
            audit_run_id=audit_run_id,
            finding_id=finding_id,
            stage="poc-verifier",
            agent_run_id=agent_run_id,
            title="PoC Verifier Report",
            payload={"verifications": [], "finding_markdown": markdown, "markdown_first": True},
        )
        return 1
    created = 0
    async with SessionLocal() as session:
        for verification in verifications:
            if str(verification.get("finding_id") or finding_id) != finding_id:
                continue
            session.add(
                Evidence(
                    evidence_id=str(uuid.uuid4()),
                    finding_id=finding_id,
                    audit_run_id=audit_run_id,
                    kind="poc-verification",
                    summary=str(verification.get("reason") or verification.get("status") or "PoC verification"),
                    payload={**verification, "agent_run_id": agent_run_id},
                )
            )
            created += 1
        await session.commit()
    await _write_finding_agent_report(
        audit_run_id=audit_run_id,
        finding_id=finding_id,
        stage="poc-verifier",
        agent_run_id=agent_run_id,
        title="PoC Verifier Report",
        payload={"verifications": verifications},
    )
    return created


async def _write_finding_agent_report(
    *,
    audit_run_id: str,
    finding_id: str,
    stage: str,
    agent_run_id: str | None,
    title: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    audit_run = await _get_audit_run(audit_run_id) or {}
    store = ArtifactStore(get_settings())
    safe_stage = _safe_report_name(stage)
    suffix = agent_run_id or uuid.uuid4().hex
    source = _finding_agent_source_artifacts(audit_run_id, agent_run_id, safe_stage)
    if source.get("report_path"):
        metadata = _copy_finding_agent_artifact(
            store=store,
            source_path=Path(str(source["report_path"])),
            destination_relative_path=f"findings/{audit_run_id}/{finding_id}/agent-reports/{safe_stage}-{suffix}.md",
            content_type="text/markdown; charset=utf-8",
        )
        report_source = "agent-written"
    else:
        text = _agent_stage_report_markdown(title=title, finding_id=finding_id, stage=stage, agent_run_id=agent_run_id, payload=payload)
        metadata = store.put_text(
            f"findings/{audit_run_id}/{finding_id}/agent-reports/{safe_stage}-{suffix}.md",
            text,
            content_type="text/markdown; charset=utf-8",
        )
        report_source = "platform-fallback"
    result_metadata: dict[str, Any] | None = None
    if source.get("json_path"):
        result_metadata = _copy_finding_agent_artifact(
            store=store,
            source_path=Path(str(source["json_path"])),
            destination_relative_path=f"findings/{audit_run_id}/{finding_id}/agent-reports/{safe_stage}-{suffix}.json",
            content_type="application/json; charset=utf-8",
        )
    await _upsert_artifact_record(
        metadata,
        [
            {
                "kind": f"finding_{safe_stage}_agent_report",
                "project_id": audit_run.get("project_id"),
                "audit_run_id": audit_run_id,
                "record_id": finding_id,
                "agent_run_id": agent_run_id,
            }
        ],
    )
    if result_metadata:
        await _upsert_artifact_record(
            result_metadata,
            [
                {
                    "kind": f"finding_{safe_stage}_agent_result",
                    "project_id": audit_run.get("project_id"),
                    "audit_run_id": audit_run_id,
                    "record_id": finding_id,
                    "agent_run_id": agent_run_id,
                }
            ],
        )
    async with SessionLocal() as session:
        session.add(
            Evidence(
                evidence_id=str(uuid.uuid4()),
                finding_id=finding_id,
                audit_run_id=audit_run_id,
                kind=f"{safe_stage}-agent-report",
                summary=f"{title} ({stage})",
                artifact_path=metadata["path"],
                payload={
                    "stage": stage,
                    "agent_run_id": agent_run_id,
                    "artifact_id": metadata["artifact_id"],
                    "report_source": report_source,
                    "agent_report_source_path": str(source["report_path"]) if source.get("report_path") else None,
                    "agent_result_artifact_id": result_metadata["artifact_id"] if result_metadata else None,
                    "agent_result_source_path": str(source["json_path"]) if source.get("json_path") else None,
                },
            )
        )
        await session.commit()
    return metadata


def _finding_agent_source_artifacts(audit_run_id: str, agent_run_id: str | None, safe_stage: str) -> dict[str, Path | None]:
    if not agent_run_id:
        return {"report_path": None, "json_path": None}
    agent_dir = get_settings().artifact_root / "agent-runs" / audit_run_id / agent_run_id
    return {
        "report_path": _existing_artifact_file(agent_dir / f"{safe_stage}-report.md"),
        "json_path": _existing_artifact_file(agent_dir / f"{safe_stage}-result.json"),
    }


def _existing_artifact_file(path: Path) -> Path | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None
    return resolved if resolved.exists() and resolved.is_file() else None


def _copy_finding_agent_artifact(
    *,
    store: ArtifactStore,
    source_path: Path,
    destination_relative_path: str,
    content_type: str,
) -> dict[str, Any]:
    data = source_path.read_bytes()
    return store.put_bytes(destination_relative_path, data, content_type=content_type)


def _poc_candidate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [item for item in findings if str(item.get("status") or "").lower() == "confirmed"]
    if candidates:
        return candidates
    return [item for item in findings if str(item.get("status") or "").lower() == "needs_review"]


async def _filter_deep_dive_findings(audit_run_id: str, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not findings:
        return []
    finding_ids = [str(item.get("finding_id") or "") for item in findings if item.get("finding_id")]
    if not finding_ids:
        return []
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(FindingTriageDecision).where(
                    FindingTriageDecision.audit_run_id == audit_run_id,
                    FindingTriageDecision.finding_id.in_(finding_ids),
                    FindingTriageDecision.decision_status == "deep_dive",
                    FindingTriageDecision.deep_dive_allowed == True,  # noqa: E712
                )
            )
        ).scalars().all()
    allowed = {str(row.finding_id) for row in rows if row.finding_id}
    return [item for item in findings if str(item.get("finding_id") or "") in allowed]


async def _filter_poc_allowed_findings(audit_run_id: str, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not findings:
        return []
    finding_ids = [str(item.get("finding_id") or "") for item in findings if item.get("finding_id")]
    if not finding_ids:
        return []
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(FindingTriageDecision).where(
                    FindingTriageDecision.audit_run_id == audit_run_id,
                    FindingTriageDecision.finding_id.in_(finding_ids),
                    FindingTriageDecision.decision_status == "deep_dive",
                    FindingTriageDecision.poc_allowed == True,  # noqa: E712
                )
            )
        ).scalars().all()
    allowed = {str(row.finding_id) for row in rows if row.finding_id}
    return [item for item in findings if str(item.get("finding_id") or "") in allowed]


def _finding_artifact_contract(audit_run_id: str, finding_id: str, stage: str) -> dict[str, Any]:
    return {
        "finding_directory": f"findings/{audit_run_id}/{finding_id}",
        "finding_markdown_path": "/finding/finding.md",
        "finding_markdown_instruction": (
            "Read /finding/finding.md before starting. After finishing, update the same file with your new evidence, "
            "decision, blockers, and handoff notes for the next Agent."
        ),
        "agent_writable_report_path": f"/artifacts/{_safe_report_name(stage)}-report.md",
        "agent_writable_json_path": f"/artifacts/{_safe_report_name(stage)}-result.json",
        "canonical_finding_markdown": f"findings/{audit_run_id}/{finding_id}/finding.md",
        "platform_canonical_directory": f"findings/{audit_run_id}/{finding_id}/agent-reports",
        "instruction": (
            "Read finding_markdown_path first. Update finding_markdown_path after your stage. "
            "Write any stage-specific narrative report to agent_writable_report_path. Structured JSON is optional; "
            "the Finding markdown is the authoritative cross-Agent handoff. "
            "The platform will preserve the Finding markdown and copy the normalized stage report into platform_canonical_directory."
        ),
    }


def _ensure_finding_state_markdown(
    audit_run_id: str,
    finding: dict[str, Any],
    *,
    evidence: list[dict[str, Any]] | None = None,
    attempts: list[dict[str, Any]] | None = None,
) -> Path:
    finding_id = str(finding.get("finding_id") or "")
    if not finding_id:
        raise ValueError("finding_id is required for finding state markdown")
    path = _finding_state_markdown_path(audit_run_id, finding_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    for child in ("agent-reports", "poc", "reports"):
        (path.parent / child).mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(_initial_finding_state_markdown(audit_run_id, finding, evidence or [], attempts or []), encoding="utf-8")
    return path


def _finding_state_markdown_path(audit_run_id: str, finding_id: str) -> Path:
    return get_settings().artifact_root / "findings" / audit_run_id / finding_id / "finding.md"


def _initial_finding_state_markdown(
    audit_run_id: str,
    finding: dict[str, Any],
    evidence: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> str:
    finding_id = str(finding.get("finding_id") or "")
    lines = [
        f"# Finding: {finding.get('title') or finding_id}",
        "",
        f"- Finding ID: `{finding_id}`",
        f"- AuditRun: `{audit_run_id}`",
        f"- Severity: `{finding.get('severity') or '-'}`",
        f"- Status: `{finding.get('status') or '-'}`",
        f"- Source: `{finding.get('source') or '-'}`",
        f"- Rule: `{finding.get('rule_id') or '-'}`",
        f"- Location: `{finding.get('file_path') or '-'}`:{finding.get('line_start') or '-'}",
        "",
        "## Description",
        "",
        str(finding.get("description") or "-"),
        "",
        "## Current Evidence",
        "",
    ]
    if evidence:
        for item in evidence:
            lines.append(f"- `{item.get('kind')}` {item.get('summary') or item.get('evidence_id') or ''}".rstrip())
    else:
        lines.append("- None recorded yet.")
    lines.extend(["", "## Validation Attempts", ""])
    if attempts:
        for item in attempts:
            lines.append(f"- Round `{item.get('round_index')}` status `{item.get('status')}` AgentRun `{item.get('agent_run_id') or '-'}`")
    else:
        lines.append("- None recorded yet.")
    lines.extend(
        [
            "",
            "## Agent Handoff Notes",
            "",
            "- Each Agent must read this file before starting and update it after finishing.",
            "- Keep updates concrete: source, sink, evidence, decision, PoC status, blockers, and next steps.",
        ]
    )
    return "\n".join(lines)


def _agent_runs_for_finding(
    agent_runs: list[dict[str, Any]],
    finding: dict[str, Any],
    evidence: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ids: set[str] = set()
    raw = finding.get("raw") if isinstance(finding.get("raw"), dict) else {}
    if raw.get("agent_run_id"):
        ids.add(str(raw["agent_run_id"]))
    for item in evidence:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        if payload.get("agent_run_id"):
            ids.add(str(payload["agent_run_id"]))
    for item in attempts:
        if item.get("agent_run_id"):
            ids.add(str(item["agent_run_id"]))
    return [run for run in agent_runs if str(run.get("agent_run_id")) in ids]


def _audit_events_for_finding(audit_events: list[dict[str, Any]], finding_id: str) -> list[dict[str, Any]]:
    result = []
    for event in audit_events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if finding_id in json.dumps(payload, ensure_ascii=False):
            result.append(event)
    return result


def _poc_markdown(*, finding: dict[str, Any], poc: dict[str, Any], agent_run_id: str | None) -> str:
    commands = poc.get("commands") if isinstance(poc.get("commands"), list) else []
    cleanup = poc.get("cleanup_steps") if isinstance(poc.get("cleanup_steps"), list) else []
    lines = [
        f"# PoC: {poc.get('title') or finding.get('title') or finding.get('finding_id')}",
        "",
        f"- Finding ID: `{finding.get('finding_id')}`",
        f"- AgentRun: `{agent_run_id or '-'}`",
        f"- Language: `{poc.get('language') or 'manual'}`",
        f"- Expected result: {poc.get('expected_result') or '-'}",
        "",
        "## Commands",
        "",
    ]
    lines.extend([f"- `{command}`" for command in commands] or ["- None."])
    lines.extend(["", "## Content", "", "```", str(poc.get("content") or ""), "```", "", "## Cleanup", ""])
    lines.extend([f"- `{command}`" for command in cleanup] or ["- None."])
    lines.extend(["", "## Safety Notes", "", str(poc.get("safety_notes") or "-")])
    return "\n".join(lines)


def _agent_stage_report_markdown(
    *,
    title: str,
    finding_id: str,
    stage: str,
    agent_run_id: str | None,
    payload: dict[str, Any],
) -> str:
    return "\n".join(
        [
            f"# {title}",
            "",
            f"- Finding ID: `{finding_id}`",
            f"- Stage: `{stage}`",
            f"- AgentRun: `{agent_run_id or '-'}`",
            "",
            "## Payload",
            "",
            "```json",
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
        ]
    )


def _finding_report_markdown(payload: dict[str, Any]) -> str:
    finding = payload["finding"]
    finding_markdown = payload.get("finding_markdown") if isinstance(payload.get("finding_markdown"), dict) else finding.get("finding_markdown")
    evidence = payload["evidence"]
    attempts = payload["validation_attempts"]
    agent_runs = payload["agent_runs"]
    lines = [
        f"# Finding Report: {finding.get('title') or finding.get('finding_id')}",
        "",
        f"- Finding ID: `{finding.get('finding_id')}`",
        f"- Severity: `{finding.get('severity')}`",
        f"- Status: `{finding.get('status')}`",
        f"- Location: `{finding.get('file_path') or '-'}`:{finding.get('line_start') or '-'}",
        f"- Source: `{finding.get('source')}`",
        f"- Tracking Markdown: `{(finding_markdown or {}).get('artifact_id') or (finding_markdown or {}).get('relative_path') or '-'}`",
        "",
        "## Description",
        "",
        str(finding.get("description") or ""),
        "",
        "## Tracking Markdown",
        "",
    ]
    if isinstance(finding_markdown, dict):
        lines.extend(
            [
                f"- Artifact ID: `{finding_markdown.get('artifact_id')}`",
                f"- Relative path: `{finding_markdown.get('relative_path')}`",
                f"- URI: `{finding_markdown.get('artifact_uri')}`",
                f"- Exists: `{finding_markdown.get('exists', True)}`",
                "",
            ]
        )
    else:
        lines.extend(["- None.", ""])
    lines.extend(
        [
            "## Agent Runs",
            "",
        ]
    )
    lines.extend([f"- `{run.get('agent_name')}` `{run.get('agent_run_id')}` status `{run.get('status')}`" for run in agent_runs] or ["- None linked."])
    lines.extend(["", "## Evidence", ""])
    for item in evidence:
        artifact = item.get("artifact") if isinstance(item.get("artifact"), dict) else {}
        payload_item = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        artifact_id = artifact.get("artifact_id") or payload_item.get("artifact_id")
        suffix_parts = []
        if artifact_id:
            suffix_parts.append(f"artifact `{artifact_id}`")
        if payload_item.get("report_source"):
            suffix_parts.append(f"source `{payload_item.get('report_source')}`")
        if payload_item.get("agent_result_artifact_id"):
            suffix_parts.append(f"result `{payload_item.get('agent_result_artifact_id')}`")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        lines.append(f"- `{item.get('kind')}` {item.get('summary') or ''}{suffix}".rstrip())
    if not evidence:
        lines.append("- None.")
    lines.extend(["", "## Validation Attempts", ""])
    for attempt in attempts:
        lines.append(f"- Round `{attempt.get('round_index')}` status `{attempt.get('status')}` AgentRun `{attempt.get('agent_run_id') or '-'}`")
    if not attempts:
        lines.append("- None.")
    lines.extend(["", "## Raw Finding", "", "```json", json.dumps(finding, ensure_ascii=False, indent=2, sort_keys=True), "```"])
    return "\n".join(lines)


def _safe_report_name(value: str) -> str:
    name = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    return "-".join(part for part in name.split("-") if part)[:80] or "artifact"


def _report_json_index_payload(
    *,
    audit_run: dict[str, Any],
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
    finding_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    reports_by_finding = {str(item.get("finding_id") or ""): item for item in finding_reports}
    finding_index: list[dict[str, Any]] = []
    for finding in findings:
        finding_id = str(finding.get("finding_id") or "")
        report = reports_by_finding.get(finding_id) or {}
        finding_index.append(
            {
                "finding_id": finding_id,
                "title": finding.get("title"),
                "severity": finding.get("severity"),
                "status": finding.get("status"),
                "file_path": finding.get("file_path"),
                "line_start": finding.get("line_start"),
                "line_end": finding.get("line_end"),
                "source": finding.get("source"),
                "report_id": report.get("report_id"),
                "markdown_path": report.get("markdown_path"),
                "json_path": report.get("json_path"),
            }
        )
    compact_summary = dict(summary)
    compact_summary.pop("finding_reports", None)
    return {
        "audit_run": audit_run,
        "summary": compact_summary,
        "finding_index": finding_index,
        "finding_reports": finding_reports,
    }


def _report_summary(
    *,
    findings: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    agent_runs: list[dict[str, Any]],
    audit_events: list[dict[str, Any]],
    dependencies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    dependencies = dependencies or []
    attempts_by_finding: dict[str, list[dict[str, Any]]] = {}
    for attempt in attempts:
        attempts_by_finding.setdefault(str(attempt.get("finding_id") or ""), []).append(attempt)
    parse_warnings = _agent_parse_warnings(agent_runs, evidence)
    tool_failures = _tool_failures(audit_events)
    validator_failures = [
        attempt
        for attempt in attempts
        if str(attempt.get("status") or "").lower() in {"failed", "cancelled"}
    ]
    unvalidated = [
        finding
        for finding in findings
        if not attempts_by_finding.get(str(finding.get("finding_id") or ""))
        and str(finding.get("status") or "").lower() in {"candidate", "validating", "needs_review"}
    ]
    return {
        "finding_count": len(findings),
        "evidence_count": len(evidence),
        "source_sink_chain_count": sum(1 for item in evidence if item.get("kind") == "source-sink-chain"),
        "poc_artifact_count": sum(1 for item in evidence if item.get("kind") == "poc-artifact"),
        "poc_verification_count": sum(1 for item in evidence if item.get("kind") == "poc-verification"),
        "validation_attempt_count": len(attempts),
        "finding_count_by_status": _count_by(findings, "status"),
        "finding_count_by_severity": _count_by(findings, "severity"),
        "validation_attempt_count_by_status": _count_by(attempts, "status"),
        "tool_failures": tool_failures,
        "tool_failure_count": len(tool_failures),
        "parse_warnings": parse_warnings,
        "parse_warning_count": len(parse_warnings),
        "validator_failures": [_compact_validation_attempt(item) for item in validator_failures],
        "validator_failure_count": len(validator_failures),
        "unvalidated_findings": len(unvalidated),
        "unvalidated_finding_ids": [str(item.get("finding_id")) for item in unvalidated],
        "dependency_coverage": _dependency_coverage(dependencies, audit_events),
    }


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _agent_parse_warnings(agent_runs: list[dict[str, Any]], evidence: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    markdown_backed_agent_runs = _markdown_backed_agent_run_ids(evidence or [])
    warnings: list[dict[str, Any]] = []
    for run in agent_runs:
        output = run.get("output_summary") if isinstance(run.get("output_summary"), dict) else {}
        ingest = output.get("structured_ingest") if isinstance(output.get("structured_ingest"), dict) else {}
        parse_status = ingest.get("structured_parse_status")
        parse_warnings = ingest.get("structured_parse_warnings") or ingest.get("warnings") or []
        agent_run_id = str(run.get("agent_run_id") or "")
        if agent_run_id in markdown_backed_agent_runs and _only_missing_structured_output(parse_status, parse_warnings):
            continue
        if parse_status in {"not_found", "parsed_with_warnings"} or parse_warnings:
            warnings.append(
                {
                    "agent_run_id": agent_run_id or run.get("agent_run_id"),
                    "agent_name": run.get("agent_name"),
                    "status": parse_status or "unknown",
                    "warnings": parse_warnings,
                }
            )
    return warnings


def _markdown_backed_agent_run_ids(evidence: list[dict[str, Any]]) -> set[str]:
    backed: set[str] = set()
    for item in evidence:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        agent_run_id = str(payload.get("agent_run_id") or "")
        if not agent_run_id:
            continue
        kind = str(item.get("kind") or "")
        if (
            kind.endswith("-agent-report")
            or kind == "validator-agent-run"
            or (payload.get("markdown_first") and kind in {"poc-artifact", "poc-verification"})
        ):
            backed.add(agent_run_id)
    return backed


def _only_missing_structured_output(parse_status: Any, parse_warnings: Any) -> bool:
    warnings = parse_warnings if isinstance(parse_warnings, list) else []
    if parse_status == "not_found":
        return all(isinstance(item, dict) and item.get("kind") == "structured_output_not_found" for item in warnings) or not warnings
    return False


def _tool_failures(audit_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for event in audit_events:
        event_type = str(event.get("event_type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type in {"sca_failed", "semgrep_failed", "semgrep_skipped", "tool_unavailable"}:
            failures.append({"event_type": event_type, "payload": payload})
            continue
        if event_type != "pipeline_step_completed":
            continue
        step = str(payload.get("step") or "")
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        if step in {"sca", "semgrep"} and (result.get("ok") is False or result.get("available") is False):
            failures.append({"event_type": event_type, "step": step, "payload": result})
    return failures


def _compact_validation_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": attempt.get("attempt_id"),
        "finding_id": attempt.get("finding_id"),
        "round_index": attempt.get("round_index"),
        "status": attempt.get("status"),
        "agent_run_id": attempt.get("agent_run_id"),
        "error": (attempt.get("result") or {}).get("error") if isinstance(attempt.get("result"), dict) else None,
    }


def _dependency_coverage(dependencies: list[dict[str, Any]], audit_events: list[dict[str, Any]]) -> dict[str, Any]:
    by_ecosystem: dict[str, int] = {}
    vulnerable_packages = 0
    vulnerability_count = 0
    for dependency in dependencies:
        ecosystem = str(dependency.get("ecosystem") or "unknown")
        by_ecosystem[ecosystem] = by_ecosystem.get(ecosystem, 0) + 1
        vuln_count = int(dependency.get("vulnerability_count") or 0)
        vulnerability_count += vuln_count
        if vuln_count:
            vulnerable_packages += 1
    sca_events = []
    for event in audit_events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event.get("event_type") == "sca_completed":
            sca_events.append(
                {
                    "status": payload.get("status"),
                    "reason": payload.get("reason"),
                    "coverage": payload.get("coverage"),
                }
            )
    return {
        "dependency_count": len(dependencies),
        "vulnerable_package_count": vulnerable_packages,
        "vulnerability_count": vulnerability_count,
        "by_ecosystem": dict(sorted(by_ecosystem.items())),
        "sca_events": sca_events,
    }


async def _run_code_batch_analysis(
    audit_run_id: str,
    project_id: str,
    workspace_path: str,
    runtime: Any,
    audit_run: dict[str, Any],
) -> dict[str, Any]:
    config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
    max_tasks = int(config.get("max_code_audit_tasks") or 8)
    max_files_per_task = int(config.get("max_files_per_code_audit_task") or 25)
    max_parallel_agents = int(config.get("max_parallel_code_auditors") or 2)
    agent_name = str(config.get("code_auditor_agent_name") or "opencode-code-auditor")
    planner = CodeAuditPlanner(workspace_path)
    plans = planner.plan(max_tasks=max_tasks, max_files_per_task=max_files_per_task)
    await _record_pipeline_event(
        audit_run_id,
        "code_analysis_plan_created",
        {
            "planned": len(plans),
            "max_tasks": max_tasks,
            "max_files_per_task": max_files_per_task,
            "max_parallel_agents": max_parallel_agents,
            "agent_name": agent_name,
        },
    )
    async with SessionLocal() as session:
        await session.execute(delete(CodeAnalysisTask).where(CodeAnalysisTask.audit_run_id == audit_run_id))
        for plan in plans:
            session.add(
                CodeAnalysisTask(
                    task_id=f"{audit_run_id}-{plan.task_id}",
                    audit_run_id=audit_run_id,
                    project_id=project_id,
                    title=plan.title,
                    focus=plan.focus,
                    file_paths=plan.file_paths,
                    status="created",
                    result={"risk_keywords": plan.risk_keywords, "metadata": plan.metadata},
                )
            )
        await session.commit()
    if not plans:
        result = {"ok": True, "available": True, "planned": 0, "completed": 0, "failed": 0, "skipped": 0}
        await _record_pipeline_event(audit_run_id, "code_analysis_completed", result)
        return result

    semaphore = asyncio.Semaphore(max(1, max_parallel_agents))

    async def mark_task(task_id: str, status: str, result: dict[str, Any], agent_run_id: str | None = None) -> None:
        async with SessionLocal() as session:
            row = await session.scalar(select(CodeAnalysisTask).where(CodeAnalysisTask.task_id == task_id))
            if row:
                row.status = status
                row.result = result
                if agent_run_id:
                    row.agent_run_id = agent_run_id
            await session.commit()

    async def run_plan(plan) -> dict[str, Any]:
        task_db_id = f"{audit_run_id}-{plan.task_id}"
        async with semaphore:
            await mark_task(task_db_id, "running", {"risk_keywords": plan.risk_keywords, "metadata": plan.metadata})
            input_payload = {
                "goal": (
                    "Perform high-recall candidate vulnerability discovery for this batch. "
                    "Do not make final vulnerability judgements. Write every plausible candidate to the shared Whiteboard as candidate_vulnerability cards."
                ),
                "audit_phase": "code-batch-analysis",
                "code_audit_task": {
                    "task_id": task_db_id,
                    "title": plan.title,
                    "focus": plan.focus,
                    "file_paths": plan.file_paths,
                    "risk_keywords": plan.risk_keywords,
                    "required_finding_fields": [
                        "title",
                        "severity",
                        "file_path",
                        "line_start",
                        "description",
                        "confidence",
                        "source",
                    ],
                },
                "codebase_memory": _codebase_memory_context(),
                "internal_tools": {
                    "semgrep": {"enabled": bool(config.get("enable_batch_internal_semgrep", True)), "mode": "agent-invoked"},
                    "sca": {"enabled": bool(config.get("enable_batch_internal_sca", True)), "mode": "agent-invoked"},
                    "codebase_memory": {"enabled": True, "repo_path": "/workspace"},
                },
                "feedback_loop": config.get("feedback_loop") if isinstance(config.get("feedback_loop"), dict) else None,
                "analysis_guidance": [
                    "Prioritize authentication, authorization, injection, file/path, SSRF, deserialization, crypto, secret handling, and business logic flaws.",
                    "Use source and decompiled source roots when STRUCTURE.md says they are available.",
                    "Use codebase-memory-mcp: call index_repository for /workspace when graph context is missing, then get_architecture, search_graph, trace_path, query_graph, get_code_snippet, detect_changes, or search_code as needed.",
                    "Create Whiteboard candidate_vulnerability cards with source metadata: source, decompiled, semgrep, sca, codebase-memory, or agent.",
                    "Prefer recall over precision. Validators will refine reachability later.",
                ],
            }
            try:
                agent_result = await runtime.start_agent_run(
                    audit_run_id=audit_run_id,
                    project_id=project_id,
                    agent_name=agent_name,
                    workspace_host_path=workspace_path,
                    allow_external_network=_effective_agent_external_network(audit_run, get_settings()),
                    retain_runtime_on_failure=bool(audit_run.get("retain_runtime_on_failure")),
                    input_payload=input_payload,
                )
            except Exception as exc:
                result = {"task_id": task_db_id, "status": "failed", "error": str(exc)}
                await mark_task(task_db_id, "failed", result)
                await _record_pipeline_event(audit_run_id, "code_analysis_task_failed", result)
                return result
            agent_run_id = str(agent_result.get("agent_run_id") or agent_result.get("run_id") or "")
            failed = str(agent_result.get("opencode_status") or "").lower() == "failed" or bool(agent_result.get("error"))
            status = "failed" if failed else "completed"
            result = {
                "task_id": task_db_id,
                "status": status,
                "agent_run_id": agent_run_id or None,
                "agent_result": _compact_event_payload(agent_result),
            }
            await mark_task(task_db_id, status, result, agent_run_id=agent_run_id or None)
            await _record_pipeline_event(audit_run_id, "code_analysis_task_completed", result)
            return result

    results = await asyncio.gather(*(run_plan(plan) for plan in plans))
    status_counts: dict[str, int] = {}
    findings_created = 0
    for result in results:
        status = str(result.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        agent_result = result.get("agent_result") if isinstance(result.get("agent_result"), dict) else {}
        ingest = agent_result.get("structured_ingest") if isinstance(agent_result.get("structured_ingest"), dict) else {}
        findings_created += int(ingest.get("findings_created") or 0)
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    final = {
        "ok": failed == 0,
        "available": True,
        "planned": len(plans),
        "completed": completed,
        "failed": failed,
        "skipped": 0,
        "status_counts": status_counts,
        "findings_created": findings_created,
        "agent_name": agent_name,
    }
    await _record_pipeline_event(audit_run_id, "code_analysis_completed", final)
    return final


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
    summary = payload.get("summary") or {}
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
        f"- Source-to-sink chains: `{summary.get('source_sink_chain_count', 0)}`",
        f"- PoC artifacts: `{summary.get('poc_artifact_count', 0)}`",
        f"- PoC verifications: `{summary.get('poc_verification_count', 0)}`",
        f"- Finding reports: `{summary.get('finding_report_count', 0)}`",
        f"- Validation attempts: `{len(attempts)}`",
        f"- Parse warnings: `{summary.get('parse_warning_count', 0)}`",
        f"- Tool failures: `{summary.get('tool_failure_count', 0)}`",
        f"- Validator failures: `{summary.get('validator_failure_count', 0)}`",
        f"- Unvalidated findings: `{summary.get('unvalidated_findings', 0)}`",
        "",
        "## Result Quality",
        "",
        "### Finding Status Counts",
        "",
    ]
    for status, count in (summary.get("finding_count_by_status") or {}).items():
        lines.append(f"- `{status}`: `{count}`")
    if not (summary.get("finding_count_by_status") or {}):
        lines.append("- No findings recorded.")
    lines.extend(["", "### Validation Attempt Counts", ""])
    for status, count in (summary.get("validation_attempt_count_by_status") or {}).items():
        lines.append(f"- `{status}`: `{count}`")
    if not (summary.get("validation_attempt_count_by_status") or {}):
        lines.append("- No validation attempts recorded.")
    lines.extend(["", "### Parse Warnings", ""])
    if summary.get("parse_warnings"):
        for warning in summary["parse_warnings"]:
            lines.append(f"- AgentRun `{warning.get('agent_run_id')}` status `{warning.get('status')}`")
    else:
        lines.append("- None.")
    lines.extend(["", "### Tool Failures", ""])
    if summary.get("tool_failures"):
        for failure in summary["tool_failures"]:
            lines.append(f"- `{failure.get('event_type')}` {failure.get('step') or ''}".rstrip())
    else:
        lines.append("- None.")
    lines.extend(["", "### Validator Failures", ""])
    if summary.get("validator_failures"):
        for failure in summary["validator_failures"]:
            lines.append(
                f"- Finding `{failure.get('finding_id')}` round `{failure.get('round_index')}` "
                f"status `{failure.get('status')}`"
            )
    else:
        lines.append("- None.")
    lines.extend(["", "### Unvalidated Findings", ""])
    if summary.get("unvalidated_finding_ids"):
        for finding_id in summary["unvalidated_finding_ids"]:
            lines.append(f"- `{finding_id}`")
    else:
        lines.append("- None.")
    coverage = summary.get("dependency_coverage") or {}
    lines.extend(["", "### Dependency Coverage", ""])
    lines.append(f"- Dependencies: `{coverage.get('dependency_count', 0)}`")
    lines.append(f"- Vulnerable packages: `{coverage.get('vulnerable_package_count', 0)}`")
    lines.append(f"- Vulnerabilities: `{coverage.get('vulnerability_count', 0)}`")
    for ecosystem, count in (coverage.get("by_ecosystem") or {}).items():
        lines.append(f"- `{ecosystem}`: `{count}`")
    lines.extend(
        [
            "",
            "## Findings",
            "",
        ]
    )
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


async def _require_admin(request: Request, settings: Settings) -> None:
    if not await auth_is_enabled(settings):
        return
    principal = getattr(request.state, "auth_principal", None)
    if not has_scope(principal, "admin"):
        raise HTTPException(status_code=403, detail="admin scope required")


def _normalize_scopes(scopes: list[str]) -> list[str]:
    return normalize_scopes(scopes, default_scope="read")


def _normalize_knowledge_scope(scope: str) -> str:
    normalized = (scope or "global").strip().lower()
    if normalized not in {"global", "project"}:
        raise HTTPException(status_code=400, detail="knowledge scope must be global or project")
    return normalized


def _knowledge_evidence_from_match(item: dict[str, Any], chunk: KnowledgeChunk) -> dict[str, Any]:
    metadata = chunk.metadata_json or {}
    return {
        "kind": "knowledge-rag",
        "summary": metadata.get("title") or item.get("title") or metadata.get("source_name") or item.get("source_name"),
        "payload": {
            "document_id": item.get("document_id") or chunk.document_id,
            "chunk_id": item.get("chunk_id") or chunk.chunk_id,
            "score": item.get("score"),
            "scope": item.get("scope") or chunk.scope,
            "project_id": item.get("project_id") or chunk.project_id,
            "chunk_index": item.get("chunk_index") if item.get("chunk_index") is not None else chunk.chunk_index,
            "title": item.get("title") or metadata.get("title"),
            "source_name": item.get("source_name") or metadata.get("source_name"),
        },
    }


__all__ = ["register_runtime_routes"]

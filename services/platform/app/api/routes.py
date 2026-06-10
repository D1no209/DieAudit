import contextlib
import json
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Body, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, select

from app.api.readiness import (
    embedding_readiness_remediation as _embedding_readiness_remediation,
    normalized_pipeline_backend as _normalized_pipeline_backend,
    pipeline_backend_readiness_check as _pipeline_backend_readiness_check,
    sandbox_readiness_remediation as _sandbox_readiness_remediation,
    summarize_readiness_checks as _summarize_readiness_checks,
    template_readiness_checks as _template_readiness_checks,
    vector_store_readiness_remediation as _vector_store_readiness_remediation,
)
from app.api.serializers import (
    agent_run_to_dict as _agent_run_to_dict,
    artifact_metadata_or_none as _artifact_metadata_or_none,
    attempt_to_dict as _attempt_to_dict,
    audit_run_to_dict as _audit_run_to_dict,
    dependency_record_to_dict as _dependency_record_to_dict,
    evidence_to_dict as _evidence_to_dict,
    finding_to_dict as _finding_to_dict,
    knowledge_chunk_from_row as _knowledge_chunk_from_row,
    knowledge_chunk_to_dict as _knowledge_chunk_to_dict,
    knowledge_document_to_dict as _knowledge_document_to_dict,
    platform_audit_event_to_dict as _platform_audit_event_to_dict,
    project_to_dict as _project_to_dict,
    report_to_dict as _report_to_dict,
    snapshot_to_dict as _snapshot_to_dict,
)
from app.domain.models import (
    AgentRun,
    AgentRunEvent,
    ApiKeyRecord,
    AuditRun,
    AuditRunEvent,
    ContainerRun,
    DependencyRecord,
    Evidence,
    Finding,
    KnowledgeChunk,
    KnowledgeDocument,
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
    CreateApiKeyRequest,
    CreateFindingRequest,
    CreateProjectRequest,
    KnowledgeSearchRequest,
    RunPocRequest,
    StartAgentRunRequest,
    StartSandboxServiceRequest,
    StorageCleanupRequest,
    TemplateBody,
    ValidatorScaleRequest,
)
from app.services.artifacts import (
    ArtifactAccessError,
    artifact_metadata,
    artifact_path_matches,
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
from app.services.dependency_scanner import DependencyScanner
from app.services.finding_dedupe import find_existing_finding, finding_identity
from app.services.knowledge import KnowledgeIndexError, KnowledgeService
from app.services.pipeline_executor import PipelineCancelled, PipelineExecutor
from app.services.pipeline_recovery import is_active_pipeline
from app.services.storage_cleanup import StorageCleanupService
from app.services.templates import TemplateStore
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
            run_sca=_run_sca_mcp,
            run_semgrep=_run_semgrep_mcp,
            judge_audit_run=_judge_audit_run_internal,
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
        return {
            "embedding": await service.embedding_health(probe=settings.knowledge_embedding_probe_on_readiness),
            "vector_store": await service.collection_health(probe=settings.knowledge_embedding_probe_on_readiness),
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
            enriched.append({**item, "text": chunk.text, "metadata": chunk.metadata_json or {}})
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
        await _mark_audit_run_status(audit_run_id, "queued")
        await _set_pipeline_state(audit_run_id, stage="queued", status="queued")
        backend = _normalized_pipeline_backend(settings)
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
        try:
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
        return artifact_metadata(settings, artifact_path)

    @router.get("/artifacts/download")
    async def download_artifact(request: Request, path: str = Query(...)) -> FileResponse:
        try:
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
        return FileResponse(artifact_path, filename=artifact_path.name, headers=secure_artifact_headers())

    @router.get("/reports/{report_id}/download")
    async def download_report(request: Request, report_id: str) -> FileResponse:
        async with SessionLocal() as session:
            report = await session.scalar(select(ReportArtifact).where(ReportArtifact.report_id == report_id))
            if not report:
                raise HTTPException(status_code=404, detail="report not found")
            try:
                path = resolve_artifact_path(settings, report.path)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail="report artifact not found")
            except ArtifactAccessError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
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
            return FileResponse(path, filename=path.name, media_type="text/markdown", headers=secure_artifact_headers())

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
        ]
        worker_health: dict[str, Any] | None = None
        if _normalized_pipeline_backend(settings) == "workflow-worker":
            worker_health = await workflow_worker_health(max_age_seconds=settings.pipeline_worker_heartbeat_ttl_seconds)
        checks.append(_pipeline_backend_readiness_check(settings, worker_health=worker_health))
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
                    "title": "Sandbox has strong isolation",
                    "status": "pass" if sandbox.get("strong_isolation_available") else "fail",
                    "detail": sandbox_detail,
                    "remediation": _sandbox_readiness_remediation(sandbox_detail),
                }
            )
        except Exception as exc:
            checks.append({
                "id": "sandbox_isolation",
                "title": "Sandbox has strong isolation",
                "status": "fail",
                "detail": str(exc),
                "remediation": [
                    "Verify Docker Engine is reachable through docker-socket-proxy, then install and configure a strong runtime such as gVisor runsc.",
                ],
            })
        knowledge_service = KnowledgeService(settings)
        embedding = await knowledge_service.embedding_health(probe=settings.knowledge_embedding_probe_on_readiness)
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
        checks.extend(_template_readiness_checks(agent_templates, mcp_templates, tool_capability_result))
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
            await _record_audit_run_event(audit_run_id, "sandbox_service_failed", {"error": str(exc), "request": body.model_dump()})
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _record_audit_run_event(audit_run_id, "sandbox_service_started", result)
        return result

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
    summary = {
        "ok": bool(osv_result.get("ok")),
        "packages": len(packages),
        "vulnerabilities": len(vulnerabilities),
        "dependency_records": dependency_records,
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
        tool_execution=_tool_result_metadata(result),
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


__all__ = ["register_runtime_routes"]

from __future__ import annotations

from typing import Any

from app.domain.models import (
    AgentRun,
    AuditRun,
    DependencyRecord,
    Evidence,
    Finding,
    KnowledgeChunk,
    KnowledgeDocument,
    PlatformAuditEvent,
    Project,
    ProjectSnapshot,
    ReportArtifact,
    CodeAnalysisTask,
    ValidationAttempt,
    WhiteboardAttachment,
    WhiteboardCard,
    WhiteboardEdge,
    WhiteboardNote,
    WhiteboardTask,
)
from app.services.artifacts import (
    ArtifactAccessError,
    artifact_absolute_path,
    artifact_id_for_relative_path,
    artifact_metadata,
    artifact_uri,
)
from app.settings import get_settings


def agent_run_to_dict(row: AgentRun) -> dict[str, Any]:
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


def platform_audit_event_to_dict(row: PlatformAuditEvent) -> dict[str, Any]:
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


def project_to_dict(row: Project) -> dict[str, Any]:
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


def snapshot_to_dict(row: ProjectSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": row.snapshot_id,
        "project_id": row.project_id,
        "source_type": row.source_type,
        "source_ref": row.source_ref,
        "workspace_path": row.workspace_path,
        "artifact_path": row.artifact_path,
        "artifact": artifact_metadata_or_none(row.artifact_path),
        "content_hash": row.content_hash,
        "status": row.status,
        "metadata": row.metadata_json,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def audit_run_to_dict(row: AuditRun) -> dict[str, Any]:
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


def finding_to_dict(row: Finding) -> dict[str, Any]:
    finding_markdown = finding_markdown_reference(row.audit_run_id, row.finding_id)
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
        "finding_markdown": finding_markdown,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def finding_markdown_reference(audit_run_id: str, finding_id: str) -> dict[str, Any]:
    settings = get_settings()
    relative_path = f"findings/{audit_run_id}/{finding_id}/finding.md"
    try:
        metadata = artifact_metadata(settings, relative_path)
        return {**metadata, "exists": True}
    except (ArtifactAccessError, FileNotFoundError, OSError):
        artifact_id = artifact_id_for_relative_path(relative_path)
        return {
            "artifact_id": artifact_id,
            "artifact_uri": artifact_uri(settings, relative_path),
            "storage_backend": getattr(settings, "artifact_storage_backend", "local"),
            "path": str(artifact_absolute_path(settings, relative_path)),
            "relative_path": relative_path,
            "name": "finding.md",
            "content_type": "text/markdown; charset=utf-8",
            "download_url": f"/artifacts/download?path={relative_path}",
            "canonical_download_url": f"/artifacts/{artifact_id}/download",
            "exists": False,
        }


def evidence_to_dict(row: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": row.evidence_id,
        "finding_id": row.finding_id,
        "audit_run_id": row.audit_run_id,
        "kind": row.kind,
        "summary": row.summary,
        "artifact_path": row.artifact_path,
        "artifact": artifact_metadata_or_none(row.artifact_path),
        "payload": row.payload,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def knowledge_document_to_dict(row: KnowledgeDocument) -> dict[str, Any]:
    return {
        "document_id": row.document_id,
        "title": row.title,
        "source_name": row.source_name,
        "content_type": row.content_type,
        "scope": row.scope,
        "project_id": row.project_id,
        "status": row.status,
        "chunk_count": row.chunk_count,
        "artifact_path": row.artifact_path,
        "artifact": artifact_metadata_or_none(row.artifact_path),
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def knowledge_chunk_to_dict(row: KnowledgeChunk) -> dict[str, Any]:
    return {
        "chunk_id": row.chunk_id,
        "document_id": row.document_id,
        "scope": row.scope,
        "project_id": row.project_id,
        "chunk_index": row.chunk_index,
        "text": row.text,
        "token_count": row.token_count,
        "vector_id": row.vector_id,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def knowledge_chunk_from_row(row: dict[str, Any]) -> KnowledgeChunk:
    return KnowledgeChunk(
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


def attempt_to_dict(row: ValidationAttempt) -> dict[str, Any]:
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


def report_to_dict(row: ReportArtifact) -> dict[str, Any]:
    return {
        "report_id": row.report_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "kind": row.kind,
        "path": row.path,
        "artifact": artifact_metadata_or_none(row.path),
        "summary": row.summary,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def dependency_record_to_dict(row: DependencyRecord) -> dict[str, Any]:
    return {
        "dependency_id": row.dependency_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "ecosystem": row.ecosystem,
        "name": row.name,
        "version": row.version,
        "manifest": row.manifest,
        "vulnerability_count": row.vulnerability_count,
        "vulnerabilities": row.vulnerabilities or [],
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def whiteboard_card_to_dict(row: WhiteboardCard, *, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "card_id": row.card_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "title": row.title,
        "card_type": row.card_type,
        "status": row.status,
        "author": row.author,
        "agent_run_id": row.agent_run_id,
        "event_time": row.event_time.isoformat() if row.event_time else None,
        "content": row.content,
        "confidence": row.confidence,
        "finding_id": row.finding_id,
        "file_path": row.file_path,
        "line_start": row.line_start,
        "line_end": row.line_end,
        "expected_predecessors": row.expected_predecessors or [],
        "possible_successors": row.possible_successors or [],
        "requirements": row.requirements or [],
        "attachments": attachments or [],
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def whiteboard_edge_to_dict(row: WhiteboardEdge) -> dict[str, Any]:
    return {
        "edge_id": row.edge_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "source_card_id": row.source_card_id,
        "target_card_id": row.target_card_id,
        "edge_type": row.edge_type,
        "author": row.author,
        "agent_run_id": row.agent_run_id,
        "rationale": row.rationale,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def whiteboard_note_to_dict(row: WhiteboardNote) -> dict[str, Any]:
    return {
        "note_id": row.note_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "card_id": row.card_id,
        "author": row.author,
        "agent_run_id": row.agent_run_id,
        "content": row.content,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def whiteboard_attachment_to_dict(row: WhiteboardAttachment) -> dict[str, Any]:
    return {
        "attachment_id": row.attachment_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "card_id": row.card_id,
        "path": row.path,
        "label": row.label,
        "content_type": row.content_type,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def whiteboard_task_to_dict(row: WhiteboardTask) -> dict[str, Any]:
    return {
        "task_id": row.task_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "gap_card_id": row.gap_card_id,
        "card_id": row.card_id,
        "agent_role": row.agent_role,
        "agent_name": row.agent_name,
        "status": row.status,
        "round_index": row.round_index,
        "attempt_index": row.attempt_index,
        "agent_run_id": row.agent_run_id,
        "parent_task_id": row.parent_task_id,
        "root_task_id": row.root_task_id,
        "wait_reason": row.wait_reason,
        "wake_event_id": row.wake_event_id,
        "task_group": row.task_group,
        "requested_by_agent_run_id": row.requested_by_agent_run_id,
        "prompt": row.prompt,
        "result": row.result or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def code_analysis_task_to_dict(row: CodeAnalysisTask) -> dict[str, Any]:
    return {
        "task_id": row.task_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "title": row.title,
        "focus": row.focus,
        "file_paths": row.file_paths or [],
        "status": row.status,
        "agent_run_id": row.agent_run_id,
        "result": row.result or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def artifact_metadata_or_none(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        return artifact_metadata(get_settings(), path)
    except (ArtifactAccessError, FileNotFoundError, OSError):
        return None

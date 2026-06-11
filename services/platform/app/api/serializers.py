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
)
from app.services.artifacts import ArtifactAccessError, artifact_metadata
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

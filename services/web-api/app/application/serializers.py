from __future__ import annotations

from typing import Any


def iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def project_to_bff(row: Any) -> dict[str, Any]:
    return {
        "project_id": row.project_id,
        "name": row.name,
        "source_type": row.source_type,
        "source_uri": row.source_uri,
        "default_branch": row.default_branch,
        "status": row.status,
        "metadata": row.metadata_json or {},
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def snapshot_to_bff(row: Any) -> dict[str, Any]:
    return {
        "snapshot_id": row.snapshot_id,
        "project_id": row.project_id,
        "source_type": row.source_type,
        "source_ref": row.source_ref,
        "workspace_path": row.workspace_path,
        "artifact_path": row.artifact_path,
        "content_hash": row.content_hash,
        "status": row.status,
        "metadata": row.metadata_json or {},
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def audit_run_to_bff(row: Any) -> dict[str, Any]:
    return {
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "snapshot_id": row.snapshot_id,
        "status": row.status,
        "pipeline_status": row.pipeline_status,
        "current_stage": row.current_stage,
        "worker_id": row.worker_id,
        "cancel_requested": row.cancel_requested,
        "workspace_path": row.workspace_path,
        "allow_external_network": row.allow_external_network,
        "retain_runtime_on_failure": row.retain_runtime_on_failure,
        "config": row.config_json or {},
        "input_payload": row.input_payload or {},
        "metadata": row.metadata_json or {},
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def agent_run_to_bff(row: Any) -> dict[str, Any]:
    return {
        "agent_run_id": row.agent_run_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "agent_name": row.agent_name,
        "template_name": row.template_name,
        "protocol_kind": row.protocol_kind,
        "status": row.status,
        "runtime_id": row.runtime_id,
        "acp_session_id": row.acp_session_id,
        "decision_status": row.decision_status,
        "decision_reason": row.decision_reason,
        "input_summary": row.input_payload or {},
        "output_summary": row.output_payload or {},
        "artifact_path": row.artifact_path,
        "error": row.error,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def agent_event_to_bff(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "agent_run_id": row.agent_run_id,
        "event_type": row.event_type,
        "payload": row.payload_json or {},
        "created_at": iso(row.created_at),
    }


def finding_to_bff(row: Any) -> dict[str, Any]:
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
        "metadata": row.metadata_json or {},
        "raw": row.raw_result or {},
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def evidence_to_bff(row: Any) -> dict[str, Any]:
    return {
        "evidence_id": row.evidence_id,
        "finding_id": row.finding_id,
        "audit_run_id": row.audit_run_id,
        "kind": row.kind,
        "summary": row.summary,
        "artifact_ids": row.artifact_ids or [],
        "payload": row.payload_json or {},
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def report_to_bff(row: Any) -> dict[str, Any]:
    return {
        "report_id": row.report_id,
        "audit_run_id": row.audit_run_id,
        "title": row.title,
        "format": row.format,
        "artifact_path": row.artifact_id,
        "artifact_id": row.artifact_id,
        "summary": row.summary_json or {},
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def code_analysis_task_to_bff(row: Any) -> dict[str, Any]:
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
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def runtime_container_to_bff(row: Any) -> dict[str, Any]:
    return {
        "Id": row.container_id,
        "Names": [row.container_name] if row.container_name else [],
        "Image": row.image,
        "State": row.status,
        "Status": row.status,
        "Labels": row.labels_json or {},
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "agent_run_id": row.agent_run_id,
        "role": row.role,
        "exit_code": row.exit_code,
        "log_artifact_id": row.log_artifact_id,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def whiteboard_card_to_bff(row: Any) -> dict[str, Any]:
    return {
        "card_id": row.card_id,
        "audit_run_id": row.audit_run_id,
        "title": row.title,
        "card_type": row.card_type,
        "status": row.status,
        "content": row.content,
        "metadata": row.metadata_json or {},
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def whiteboard_edge_to_bff(row: Any) -> dict[str, Any]:
    return {
        "edge_id": row.edge_id,
        "audit_run_id": row.audit_run_id,
        "source_card_id": row.source_card_id,
        "target_card_id": row.target_card_id,
        "edge_type": row.edge_type,
        "metadata": row.metadata_json or {},
        "created_at": iso(row.created_at),
    }


def whiteboard_task_to_bff(row: Any) -> dict[str, Any]:
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
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }

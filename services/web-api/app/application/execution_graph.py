from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dieaudit_common.domain.models import (
    AgentRun,
    AuditEvent,
    AuditRun,
    Evidence,
    Finding,
    PipelineStageRun,
    Report,
    RuntimeContainer,
    WhiteboardCard,
    WhiteboardEdge,
)


PIPELINE_STAGES = [
    "snapshot-ready",
    "structure-discovery",
    "agent-audit",
    "code-analysis",
    "value-triage",
    "whiteboard-swarm",
    "validation-judgement",
    "feedback-loop",
    "poc-writing",
    "poc-verification",
    "report",
    "runtime-cleanup",
]


async def audit_run_execution_graph(session: AsyncSession, audit_run_id: str) -> dict[str, Any] | None:
    audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
    if audit_run is None:
        return None

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    edge_keys: set[tuple[str, str, str]] = set()

    def add_node(node: dict[str, Any]) -> None:
        nodes[node["id"]] = node

    def add_edge(source: str, target: str, edge_type: str, **metadata: Any) -> None:
        if source not in nodes or target not in nodes:
            return
        key = (source, target, edge_type)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edge = {"source": source, "target": target, "type": edge_type}
        if metadata:
            edge["data"] = metadata
        edges.append(edge)

    root_id = f"audit-run:{audit_run.audit_run_id}"
    add_node(
        {
            "id": root_id,
            "kind": "audit-run",
            "label": audit_run.audit_run_id,
            "status": audit_run.status,
            "group": audit_run.pipeline_status,
            "target": {"view": "audit-runs", "audit_run_id": audit_run.audit_run_id},
            "data": _audit_run_data(audit_run),
        }
    )

    stage_rows = (
        await session.execute(
            select(PipelineStageRun).where(PipelineStageRun.audit_run_id == audit_run_id).order_by(PipelineStageRun.created_at.asc())
        )
    ).scalars().all()
    event_rows = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.audit_run_id == audit_run_id).order_by(AuditEvent.created_at.asc())
        )
    ).scalars().all()

    stage_status = _stage_statuses(stage_rows, event_rows)
    stage_nodes: dict[str, str] = {}
    for stage in PIPELINE_STAGES:
        node_id = f"pipeline-step:{stage}"
        stage_nodes[stage] = node_id
        add_node(
            {
                "id": node_id,
                "kind": "pipeline-step",
                "label": _stage_label(stage),
                "status": stage_status.get(stage, "pending"),
                "group": "pipeline",
                "target": {"view": "audit-runs", "audit_run_id": audit_run_id},
                "data": {"stage": stage},
            }
        )
        add_edge(root_id, node_id, "contains")
    for previous, current in zip(PIPELINE_STAGES, PIPELINE_STAGES[1:]):
        add_edge(stage_nodes[previous], stage_nodes[current], "next")

    agent_rows = (
        await session.execute(select(AgentRun).where(AgentRun.audit_run_id == audit_run_id).order_by(AgentRun.created_at.asc()))
    ).scalars().all()
    for agent in agent_rows:
        node_id = f"agent-run:{agent.agent_run_id}"
        add_node(
            {
                "id": node_id,
                "kind": "agent-run",
                "label": agent.agent_name,
                "status": agent.status,
                "group": agent.template_name,
                "target": {"view": "agent-runs", "audit_run_id": audit_run_id, "agent_run_id": agent.agent_run_id},
                "data": _agent_data(agent),
            }
        )
        add_edge(_agent_stage_node(agent.agent_name, stage_nodes) or root_id, node_id, "runs")

    container_rows = (
        await session.execute(
            select(RuntimeContainer).where(RuntimeContainer.audit_run_id == audit_run_id).order_by(RuntimeContainer.created_at.asc())
        )
    ).scalars().all()
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
                "data": _container_data(container),
            }
        )
        source = f"agent-run:{container.agent_run_id}" if container.agent_run_id else root_id
        add_edge(source, node_id, "container")

    finding_rows = (
        await session.execute(select(Finding).where(Finding.audit_run_id == audit_run_id).order_by(Finding.created_at.asc()))
    ).scalars().all()
    for finding in finding_rows:
        node_id = f"finding:{finding.finding_id}"
        add_node(
            {
                "id": node_id,
                "kind": "finding",
                "label": finding.title,
                "status": finding.status,
                "group": finding.severity,
                "target": {"view": "findings", "audit_run_id": audit_run_id, "finding_id": finding.finding_id},
                "data": _finding_data(finding),
            }
        )
        add_edge(stage_nodes["code-analysis"], node_id, "produces")

    evidence_rows = (
        await session.execute(select(Evidence).where(Evidence.audit_run_id == audit_run_id).order_by(Evidence.created_at.asc()))
    ).scalars().all()
    for evidence in evidence_rows:
        node_id = f"evidence:{evidence.evidence_id}"
        add_node(
            {
                "id": node_id,
                "kind": "evidence",
                "label": evidence.summary or evidence.kind,
                "status": evidence.kind,
                "group": "evidence",
                "target": {"view": "findings", "audit_run_id": audit_run_id},
                "data": _evidence_data(evidence),
            }
        )
        if evidence.finding_id:
            add_edge(f"finding:{evidence.finding_id}", node_id, "validates")
        else:
            add_edge(root_id, node_id, "produces")

    report_rows = (
        await session.execute(select(Report).where(Report.audit_run_id == audit_run_id).order_by(Report.created_at.asc()))
    ).scalars().all()
    for report in report_rows:
        node_id = f"report:{report.report_id}"
        add_node(
            {
                "id": node_id,
                "kind": "report",
                "label": report.title,
                "status": report.format,
                "group": "report",
                "target": {"view": "reports", "audit_run_id": audit_run_id, "report_id": report.report_id},
                "data": _report_data(report),
            }
        )
        add_edge(stage_nodes["report"], node_id, "reports")

    card_rows = (
        await session.execute(
            select(WhiteboardCard).where(WhiteboardCard.audit_run_id == audit_run_id).order_by(WhiteboardCard.created_at.asc())
        )
    ).scalars().all()
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
                "data": _card_data(card),
            }
        )
        add_edge(stage_nodes["whiteboard-swarm"], node_id, "writes")

    whiteboard_edges = (
        await session.execute(
            select(WhiteboardEdge).where(WhiteboardEdge.audit_run_id == audit_run_id).order_by(WhiteboardEdge.created_at.asc())
        )
    ).scalars().all()
    for edge in whiteboard_edges:
        add_edge(
            f"whiteboard-card:{edge.source_card_id}",
            f"whiteboard-card:{edge.target_card_id}",
            f"whiteboard:{edge.edge_type}",
            edge_id=edge.edge_id,
            metadata=edge.metadata_json or {},
        )

    node_list = list(nodes.values())
    return {
        "audit_run_id": audit_run_id,
        "project_id": audit_run.project_id,
        "summary": execution_graph_summary(node_list),
        "nodes": node_list,
        "edges": edges,
    }


def execution_graph_summary(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for node in nodes:
        kind = str(node.get("kind") or "unknown")
        status = str(node.get("status") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
    unfinished = {"created", "pending", "queued", "running", "open", "needs_agent", "agent_queued", "starting"}
    completed = {"completed", "succeeded", "confirmed", "closed", "markdown", "json"}
    failed = {"failed", "cancelled"}
    return {
        "node_count": len(nodes),
        "by_kind": by_kind,
        "by_status": by_status,
        "completed": sum(count for status, count in by_status.items() if status in completed),
        "unfinished": sum(count for status, count in by_status.items() if status in unfinished),
        "failed": sum(count for status, count in by_status.items() if status in failed),
    }


def _stage_statuses(stage_rows: list[PipelineStageRun], event_rows: list[AuditEvent]) -> dict[str, str]:
    statuses: dict[str, str] = {row.stage: row.status for row in stage_rows}
    for event in event_rows:
        payload = event.payload_json or {}
        stage = str(payload.get("stage") or payload.get("step") or "")
        if not stage:
            continue
        if event.event_type.endswith(".started") or event.event_type.endswith("_started"):
            statuses[stage] = "running"
        elif event.event_type.endswith(".completed") or event.event_type.endswith("_completed"):
            statuses[stage] = str(payload.get("status") or "completed")
        elif event.event_type.endswith(".failed") or event.event_type.endswith("_failed"):
            statuses[stage] = "failed"
        elif event.event_type.endswith("_skipped"):
            statuses[stage] = "skipped"
    return statuses


def _agent_stage_node(agent_name: str, stage_nodes: dict[str, str]) -> str | None:
    normalized = agent_name.lower()
    mapping = [
        ("orchestrator", "agent-audit"),
        ("code-auditor", "code-analysis"),
        ("trace", "whiteboard-swarm"),
        ("source-sink", "whiteboard-swarm"),
        ("validator", "validation-judgement"),
        ("judger", "validation-judgement"),
        ("poc-writer", "poc-writing"),
        ("poc-verifier", "poc-verification"),
    ]
    for needle, stage in mapping:
        if needle in normalized:
            return stage_nodes.get(stage)
    return None


def _stage_label(stage: str) -> str:
    return {
        "poc-writing": "PoC Writing",
        "poc-verification": "PoC Verification",
        "validation-judgement": "Validation Judgement",
        "whiteboard-swarm": "Whiteboard Swarm",
    }.get(stage, stage.replace("-", " ").title())


def _audit_run_data(row: AuditRun) -> dict[str, Any]:
    return {
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "snapshot_id": row.snapshot_id,
        "pipeline_status": row.pipeline_status,
        "current_stage": row.current_stage,
    }


def _agent_data(row: AgentRun) -> dict[str, Any]:
    return {
        "agent_run_id": row.agent_run_id,
        "agent_name": row.agent_name,
        "template_name": row.template_name,
        "protocol_kind": row.protocol_kind,
        "runtime_id": row.runtime_id,
        "error": row.error,
    }


def _container_data(row: RuntimeContainer) -> dict[str, Any]:
    return {
        "container_id": row.container_id,
        "container_name": row.container_name,
        "agent_run_id": row.agent_run_id,
        "image": row.image,
        "role": row.role,
        "status": row.status,
        "exit_code": row.exit_code,
        "log_artifact_id": row.log_artifact_id,
    }


def _finding_data(row: Finding) -> dict[str, Any]:
    return {
        "finding_id": row.finding_id,
        "severity": row.severity,
        "status": row.status,
        "file_path": row.file_path,
        "line_start": row.line_start,
        "source": row.source,
    }


def _evidence_data(row: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": row.evidence_id,
        "finding_id": row.finding_id,
        "kind": row.kind,
        "artifact_ids": row.artifact_ids or [],
    }


def _report_data(row: Report) -> dict[str, Any]:
    return {
        "report_id": row.report_id,
        "format": row.format,
        "artifact_id": row.artifact_id,
        "summary": row.summary_json or {},
    }


def _card_data(row: WhiteboardCard) -> dict[str, Any]:
    return {
        "card_id": row.card_id,
        "card_type": row.card_type,
        "status": row.status,
        "content": row.content,
        "metadata": row.metadata_json or {},
    }

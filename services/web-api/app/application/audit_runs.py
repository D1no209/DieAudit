from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dieaudit_common.domain.models import (
    AgentRun,
    AgentRunEvent,
    AuditRun,
    Evidence,
    Finding,
    PipelineStageRun,
    ProjectSnapshot,
    Report,
    RuntimeContainer,
    WhiteboardCard,
    WhiteboardEdge,
    WorkerHeartbeat,
)
from dieaudit_common.persistence.repositories import AuditRunRepository

from app.application.execution_graph import audit_run_execution_graph
from app.application.agent_model_profiles import AgentModelProfileApplication
from app.application.serializers import (
    agent_event_to_bff,
    agent_run_to_bff,
    audit_run_to_bff,
    evidence_to_bff,
    finding_to_bff,
    report_to_bff,
    runtime_container_to_bff,
    whiteboard_card_to_bff,
    whiteboard_edge_to_bff,
)


class AuditRunApplication:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit_runs = AuditRunRepository(session)

    async def list_audit_runs(self) -> list[dict[str, Any]]:
        return [audit_run_to_bff(row) for row in await self.audit_runs.list()]

    async def create_audit_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        snapshot = await self._resolve_snapshot(payload["project_id"], payload.get("snapshot_id"))
        config = await self._normalized_config(payload, snapshot)
        row = await self.audit_runs.create(
            project_id=payload["project_id"],
            snapshot_id=snapshot.snapshot_id,
            workspace_path=snapshot.workspace_path,
            allow_external_network=bool(payload.get("allow_external_network")),
            retain_runtime_on_failure=bool(payload.get("retain_runtime_on_failure")),
            input_payload=payload.get("input_payload") or {},
            config=config,
        )
        return audit_run_to_bff(row)

    async def get_audit_run(self, audit_run_id: str) -> dict[str, Any] | None:
        row = await self.audit_runs.get(audit_run_id)
        return audit_run_to_bff(row) if row else None

    async def queue_audit_run(self, audit_run_id: str) -> dict[str, Any] | None:
        await self.audit_runs.queue(audit_run_id)
        row = await self.audit_runs.get(audit_run_id)
        return audit_run_to_bff(row) if row else None

    async def cancel_audit_run(self, audit_run_id: str, reason: str) -> dict[str, Any] | None:
        await self.audit_runs.cancel(audit_run_id, reason)
        row = await self.audit_runs.get(audit_run_id)
        return audit_run_to_bff(row) if row else None

    async def bundle(self, audit_run_id: str) -> dict[str, Any] | None:
        row = await self.audit_runs.get(audit_run_id)
        if row is None:
            return None
        graph = await audit_run_execution_graph(self.session, audit_run_id)
        return {
            "run": audit_run_to_bff(row),
            "agents": await self.agent_runs(audit_run_id),
            "findings": await self.findings(audit_run_id),
            "evidence": await self.evidence(audit_run_id),
            "codeAnalysisTasks": await self.code_analysis_tasks(audit_run_id),
            "dependencies": {"audit_run_id": audit_run_id, "packages": [], "summary": {"total": 0, "vulnerable": 0, "by_ecosystem": {}}},
            "containers": await self.containers(audit_run_id),
            "reports": await self.reports(audit_run_id),
            "pipeline": await self.pipeline_status(audit_run_id),
            "whiteboard": await self.whiteboard(audit_run_id),
            "executionGraph": graph,
        }

    async def agent_runs(self, audit_run_id: str) -> list[dict[str, Any]]:
        rows = await self.session.execute(select(AgentRun).where(AgentRun.audit_run_id == audit_run_id).order_by(AgentRun.created_at.desc()))
        return [agent_run_to_bff(row) for row in rows.scalars()]

    async def agent_events(self, agent_run_id: str) -> list[dict[str, Any]]:
        rows = await self.session.execute(select(AgentRunEvent).where(AgentRunEvent.agent_run_id == agent_run_id).order_by(AgentRunEvent.created_at.asc(), AgentRunEvent.id.asc()))
        return [agent_event_to_bff(row) for row in rows.scalars()]

    async def findings(self, audit_run_id: str) -> list[dict[str, Any]]:
        rows = await self.session.execute(select(Finding).where(Finding.audit_run_id == audit_run_id).order_by(Finding.created_at.desc()))
        return [finding_to_bff(row) for row in rows.scalars()]

    async def finding(self, finding_id: str) -> dict[str, Any] | None:
        row = await self.session.scalar(select(Finding).where(Finding.finding_id == finding_id))
        if row is None:
            return None
        evidence = await self.evidence(row.audit_run_id, finding_id=finding_id)
        return {**finding_to_bff(row), "evidence": evidence}

    async def evidence(self, audit_run_id: str, *, finding_id: str | None = None) -> list[dict[str, Any]]:
        query = select(Evidence).where(Evidence.audit_run_id == audit_run_id)
        if finding_id:
            query = query.where(Evidence.finding_id == finding_id)
        rows = await self.session.execute(query.order_by(Evidence.created_at.desc()))
        return [evidence_to_bff(row) for row in rows.scalars()]

    async def code_analysis_tasks(self, audit_run_id: str) -> list[dict[str, Any]]:
        return []

    async def containers(self, audit_run_id: str) -> list[dict[str, Any]]:
        rows = await self.session.execute(select(RuntimeContainer).where(RuntimeContainer.audit_run_id == audit_run_id).order_by(RuntimeContainer.created_at.desc()))
        return [runtime_container_to_bff(row) for row in rows.scalars()]

    async def reports(self, audit_run_id: str) -> list[dict[str, Any]]:
        rows = await self.session.execute(select(Report).where(Report.audit_run_id == audit_run_id).order_by(Report.created_at.desc()))
        return [report_to_bff(row) for row in rows.scalars()]

    async def whiteboard(self, audit_run_id: str) -> dict[str, Any]:
        cards = (await self.session.execute(select(WhiteboardCard).where(WhiteboardCard.audit_run_id == audit_run_id).order_by(WhiteboardCard.created_at.asc()))).scalars()
        edges = (await self.session.execute(select(WhiteboardEdge).where(WhiteboardEdge.audit_run_id == audit_run_id).order_by(WhiteboardEdge.created_at.asc()))).scalars()
        return {
            "audit_run_id": audit_run_id,
            "cards": [whiteboard_card_to_bff(row) for row in cards],
            "edges": [whiteboard_edge_to_bff(row) for row in edges],
            "tasks": [],
            "notifications": [],
        }

    async def pipeline_status(self, audit_run_id: str) -> dict[str, Any]:
        row = await self.audit_runs.get(audit_run_id)
        stages = (
            await self.session.execute(
                select(PipelineStageRun).where(PipelineStageRun.audit_run_id == audit_run_id).order_by(PipelineStageRun.created_at.asc())
            )
        ).scalars()
        stage_rows = [
            {
                "stage": stage.stage,
                "status": stage.status,
                "summary": stage.summary_json or {},
                "artifact_ids": stage.artifact_ids or [],
                "error": stage.error,
                "started_at": stage.started_at.isoformat() if stage.started_at else None,
                "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
            }
            for stage in stages
        ]
        return {
            "audit_run_id": audit_run_id,
            "status": row.pipeline_status if row else "unknown",
            "current_stage": row.current_stage if row else None,
            "runtime_control": ((row.config_json or {}).get("runtime_control") if row else {}) or {},
            "stages": stage_rows,
            "summary": {
                "completed": sum(1 for item in stage_rows if item["status"] in {"succeeded", "completed"}),
                "failed": sum(1 for item in stage_rows if item["status"] == "failed"),
                "unfinished": sum(1 for item in stage_rows if item["status"] in {"running", "queued", "pending"}),
            },
        }

    async def worker_heartbeats(self) -> dict[str, Any]:
        rows = (await self.session.execute(select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen_at.desc()))).scalars()
        return {
            "workers": [
                {
                    "worker_id": row.worker_id,
                    "service_name": row.service_name,
                    "hostname": row.hostname,
                    "status": row.status,
                    "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                    "current_audit_run_id": row.current_audit_run_id,
                    "metadata": row.metadata_json or {},
                }
                for row in rows
            ]
        }

    async def _resolve_snapshot(self, project_id: str, snapshot_id: str | None) -> ProjectSnapshot:
        query = select(ProjectSnapshot).where(ProjectSnapshot.project_id == project_id, ProjectSnapshot.status == "ready")
        if snapshot_id:
            query = query.where(ProjectSnapshot.snapshot_id == snapshot_id)
        else:
            query = query.order_by(ProjectSnapshot.created_at.desc())
        snapshot = await self.session.scalar(query)
        if snapshot is None:
            raise ValueError("project has no ready snapshot")
        return snapshot

    async def _normalized_config(self, payload: dict[str, Any], snapshot: ProjectSnapshot) -> dict[str, Any]:
        config = await AgentModelProfileApplication(self.session).merge_model_overrides(dict(payload.get("config") or {}))
        enabled_agents = payload.get("enabled_agents")
        if enabled_agents is not None:
            config["enabled_agents"] = enabled_agents
        config["workspace_host_path"] = snapshot.workspace_path
        config.setdefault("enable_whiteboard", True)
        config.setdefault("enable_whiteboard_swarm", True)
        swarm = dict(config.get("whiteboard_swarm") or {})
        trace_worker = dict(swarm.get("trace_worker") or {})
        trace_worker.setdefault("enabled", True)
        trace_worker.setdefault("agent_name", "kimi-source-sink-finder")
        trace_worker.setdefault("max_parallel", 1)
        trace_worker.setdefault("max_findings", 50)
        swarm["trace_worker"] = trace_worker
        config["whiteboard_swarm"] = swarm
        return config

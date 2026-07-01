from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dieaudit_common.domain.models import AuditRun, Finding, Report
from dieaudit_common.persistence.repositories import new_id

from app.application.clients import InternalClients
from app.pipeline.context import PipelineContext


class StageAdapterRunner:
    def __init__(self, session: AsyncSession, clients: InternalClients | None = None) -> None:
        self.session = session
        self.clients = clients or InternalClients()

    async def __call__(self, ctx: PipelineContext, stage: str) -> dict[str, Any]:
        audit_run = await self._audit_run(ctx.audit_run_id)
        if stage == "snapshot-ready":
            return await self._snapshot_ready(audit_run)
        if stage == "structure-discovery":
            return await self._structure_discovery(audit_run)
        if stage == "agent-audit":
            return await self._agent_audit(audit_run)
        if stage == "code-analysis":
            return await self._code_analysis(audit_run)
        if stage == "value-triage":
            return {"ok": True, "mode": "pre-swarm", "policy": "exclude standalone low-impact hygiene findings from swarm scheduling"}
        if stage == "whiteboard-swarm":
            return await self._whiteboard_swarm(audit_run)
        if stage == "validation-judgement":
            return await self._validation_judgement(audit_run)
        if stage == "feedback-loop":
            return {"ok": True, "mode": "single-pass", "scheduled": 0}
        if stage == "poc-writing":
            return await self._poc_agent_stage(audit_run, "poc-writer")
        if stage == "poc-verification":
            return await self._poc_agent_stage(audit_run, "poc-verifier")
        if stage == "report":
            return await self._report(audit_run)
        if stage == "runtime-cleanup":
            return await self._runtime_cleanup(audit_run)
        raise RuntimeError(f"unknown stage: {stage}")

    async def _audit_run(self, audit_run_id: str) -> AuditRun:
        row = await self.session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
        if row is None:
            raise RuntimeError("audit run not found")
        return row

    async def _snapshot_ready(self, audit_run: AuditRun) -> dict[str, Any]:
        workspace_path = audit_run.workspace_path or (audit_run.config_json or {}).get("workspace_host_path")
        if not audit_run.snapshot_id or not workspace_path:
            raise RuntimeError("audit run has no ready snapshot/workspace")
        audit_run.workspace_path = workspace_path
        audit_run.config_json = {**(audit_run.config_json or {}), "workspace_host_path": workspace_path}
        return {"ok": True, "snapshot_id": audit_run.snapshot_id, "workspace_path": workspace_path}

    async def _structure_discovery(self, audit_run: AuditRun) -> dict[str, Any]:
        workspace_path = self._workspace_path(audit_run)
        result = await self.clients.workspace_structure(workspace_path)
        audit_run.config_json = {**(audit_run.config_json or {}), "structure_context": result}
        return {"ok": bool(result.get("exists", True)), "structure": result}

    async def _agent_audit(self, audit_run: AuditRun) -> dict[str, Any]:
        config = audit_run.config_json or {}
        if not self._agent_enabled(config, "orchestrator"):
            return {"ok": True, "skipped": True, "reason": "orchestrator disabled"}
        payload = self._agent_payload(audit_run, config.get("agent_name") or "kimi-orchestrator", "agent-audit")
        return await self.clients.start_agent_run(payload)

    async def _code_analysis(self, audit_run: AuditRun) -> dict[str, Any]:
        config = audit_run.config_json or {}
        if config.get("enable_code_batch_analysis") is False or not self._agent_enabled(config, "code-auditor"):
            return {"ok": True, "skipped": True, "reason": "code analysis disabled"}
        payload = self._agent_payload(audit_run, config.get("code_auditor_agent_name") or "kimi-code-auditor", "code-analysis")
        return await self.clients.start_agent_run(payload)

    async def _whiteboard_swarm(self, audit_run: AuditRun) -> dict[str, Any]:
        config = audit_run.config_json or {}
        if config.get("enable_whiteboard") is False or config.get("enable_whiteboard_swarm") is False:
            return {"ok": True, "skipped": True, "reason": "whiteboard swarm disabled"}
        trace_worker = ((config.get("whiteboard_swarm") or {}).get("trace_worker") or {})
        return {"ok": True, "scheduled": 0, "trace_worker": trace_worker, "mode": "controller-ready"}

    async def _validation_judgement(self, audit_run: AuditRun) -> dict[str, Any]:
        config = audit_run.config_json or {}
        if config.get("enable_validation_judgement") is False:
            return {"ok": True, "skipped": True, "reason": "validation disabled"}
        findings = (await self.session.execute(select(Finding).where(Finding.audit_run_id == audit_run.audit_run_id))).scalars().all()
        if not findings:
            return {"ok": True, "scheduled": 0, "reason": "no findings"}
        payload = self._agent_payload(audit_run, config.get("validation_judgement_agent_name") or config.get("validator_agent_name") or "kimi-validator", "validation-judgement")
        payload["input_payload"]["findings"] = [
            {"finding_id": row.finding_id, "title": row.title, "severity": row.severity, "description": row.description}
            for row in findings
        ]
        return await self.clients.start_agent_run(payload)

    async def _poc_agent_stage(self, audit_run: AuditRun, role: str) -> dict[str, Any]:
        config = audit_run.config_json or {}
        if role == "poc-writer" and config.get("enable_poc_writing") is False:
            return {"ok": True, "skipped": True, "reason": "poc writing disabled"}
        if role == "poc-verifier" and config.get("enable_poc_verification") is False:
            return {"ok": True, "skipped": True, "reason": "poc verification disabled"}
        findings = (await self.session.execute(select(Finding).where(Finding.audit_run_id == audit_run.audit_run_id))).scalars().all()
        if not findings:
            return {"ok": True, "scheduled": 0, "reason": "no findings"}
        name_key = "poc_writer_agent_name" if role == "poc-writer" else "poc_verifier_agent_name"
        payload = self._agent_payload(audit_run, config.get(name_key) or f"kimi-{role}", role)
        return await self.clients.start_agent_run(payload)

    async def _report(self, audit_run: AuditRun) -> dict[str, Any]:
        findings = (await self.session.execute(select(Finding).where(Finding.audit_run_id == audit_run.audit_run_id))).scalars().all()
        report = Report(
            report_id=new_id("report"),
            audit_run_id=audit_run.audit_run_id,
            title="DieAudit Report",
            format="markdown",
            artifact_id=None,
            summary_json={"finding_count": len(findings), "status": "generated"},
        )
        self.session.add(report)
        return {"ok": True, "report_id": report.report_id, "summary": report.summary_json}

    async def _runtime_cleanup(self, audit_run: AuditRun) -> dict[str, Any]:
        if audit_run.retain_runtime_on_failure and audit_run.status == "failed":
            return {"ok": True, "skipped": True, "reason": "retain_runtime_on_failure"}
        try:
            return await self.clients.cleanup_runtime(audit_run.audit_run_id)
        except Exception as exc:
            return {"ok": False, "warning": str(exc)}

    def _agent_payload(self, audit_run: AuditRun, agent_name: str, phase: str) -> dict[str, Any]:
        return {
            "audit_run_id": audit_run.audit_run_id,
            "project_id": audit_run.project_id,
            "agent_name": agent_name,
            "workspace_host_path": self._workspace_path(audit_run),
            "allow_external_network": audit_run.allow_external_network,
            "retain_runtime_on_failure": audit_run.retain_runtime_on_failure,
            "input_payload": {
                **(audit_run.input_payload or {}),
                "audit_phase": phase,
                "config": audit_run.config_json or {},
            },
        }

    def _workspace_path(self, audit_run: AuditRun) -> str:
        workspace_path = audit_run.workspace_path or (audit_run.config_json or {}).get("workspace_host_path")
        if not workspace_path:
            raise RuntimeError("audit run has no workspace path")
        return str(workspace_path)

    @staticmethod
    def _agent_enabled(config: dict[str, Any], role: str) -> bool:
        enabled = config.get("enabled_agents")
        return not isinstance(enabled, list) or not enabled or role in enabled

from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.settings import Settings


class PipelineCancelled(RuntimeError):
    pass


AsyncCallback = Callable[..., Awaitable[Any]]


class PipelineExecutor:
    def __init__(
        self,
        *,
        settings: Settings,
        runtime: Any,
        get_audit_run: AsyncCallback,
        mark_audit_run_status: AsyncCallback,
        set_pipeline_state: AsyncCallback,
        record_audit_run_event: AsyncCallback,
        record_pipeline_event: AsyncCallback,
        record_pipeline_summary: AsyncCallback,
        raise_if_cancelled: AsyncCallback,
        is_cancel_requested: AsyncCallback,
        cancel_reason: AsyncCallback,
        list_findings: AsyncCallback,
        run_sca: AsyncCallback,
        run_semgrep: AsyncCallback,
        judge_audit_run: AsyncCallback,
        generate_report: AsyncCallback,
        compact_event_payload: Callable[[Any], Any],
    ) -> None:
        self.settings = settings
        self.runtime = runtime
        self.get_audit_run = get_audit_run
        self.mark_audit_run_status = mark_audit_run_status
        self.set_pipeline_state = set_pipeline_state
        self.record_audit_run_event = record_audit_run_event
        self.record_pipeline_event = record_pipeline_event
        self.record_pipeline_summary = record_pipeline_summary
        self.raise_if_cancelled = raise_if_cancelled
        self.is_cancel_requested = is_cancel_requested
        self.cancel_reason = cancel_reason
        self.list_findings = list_findings
        self.run_sca = run_sca
        self.run_semgrep = run_semgrep
        self.judge_audit_run = judge_audit_run
        self.generate_report = generate_report
        self.compact_event_payload = compact_event_payload

    async def execute(self, audit_run_id: str) -> None:
        audit_run = await self.get_audit_run(audit_run_id)
        if not audit_run:
            return
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        if not workspace_path:
            await self.mark_audit_run_status(audit_run_id, "failed")
            await self.set_pipeline_state(audit_run_id, stage="failed", status="failed", error="audit run has no workspace path")
            await self.record_audit_run_event(audit_run_id, "pipeline_failed", {"error": "audit run has no workspace path"})
            await self._cleanup_terminal_runtime(audit_run_id, terminal_status="failed", audit_run=audit_run)
            return
        await self.mark_audit_run_status(audit_run_id, "running")
        await self.set_pipeline_state(audit_run_id, stage="agent-audit", status="running")
        await self.record_audit_run_event(audit_run_id, "pipeline_started", {"stage": "agent-audit"})
        steps: list[dict[str, Any]] = []
        try:
            await self.raise_if_cancelled(audit_run_id)
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "agent-audit"})
            agent_result = await self.runtime.start_agent_run(
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
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": "agent-audit", "result": self.compact_event_payload(agent_result)},
            )
            await self.raise_if_cancelled(audit_run_id)

            await self.set_pipeline_state(audit_run_id, stage="sca", status="running")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "sca"})
            try:
                sca_result = await self.run_sca(audit_run_id, audit_run["project_id"], workspace_path, self.runtime, audit_run)
            except Exception as exc:
                sca_result = {"ok": False, "error": str(exc)}
                await self.record_pipeline_event(audit_run_id, "sca_failed", sca_result)
            steps.append({"step": "sca", "result": sca_result})
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": "sca", "result": self.compact_event_payload(sca_result)},
            )
            await self.raise_if_cancelled(audit_run_id)

            await self.set_pipeline_state(audit_run_id, stage="semgrep", status="running")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "semgrep"})
            try:
                semgrep_result = await self.run_semgrep(audit_run_id, audit_run["project_id"], workspace_path, self.runtime, audit_run)
            except Exception as exc:
                semgrep_result = {"ok": False, "error": str(exc)}
                await self.record_pipeline_event(audit_run_id, "semgrep_failed", semgrep_result)
            steps.append({"step": "semgrep", "result": semgrep_result})
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": "semgrep", "result": self.compact_event_payload(semgrep_result)},
            )
            await self.raise_if_cancelled(audit_run_id)

            findings = await self.list_findings(audit_run_id)
            await self.set_pipeline_state(audit_run_id, stage="validators", status="running")
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_started",
                {"step": "validators", "finding_count": len(findings), "validator_rounds": audit_run["validator_rounds"]},
            )
            validator_result = await self.runtime.scale_validators(
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
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": "validators", "result": self.compact_event_payload(validator_result)},
            )
            await self.raise_if_cancelled(audit_run_id)

            await self.set_pipeline_state(audit_run_id, stage="judgement", status="running")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "judgement"})
            judge_result = await self.judge_audit_run(audit_run_id, self.runtime)
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": "judgement", "result": self.compact_event_payload(judge_result)},
            )
            await self.raise_if_cancelled(audit_run_id)
            await self.set_pipeline_state(audit_run_id, stage="report", status="running")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "report"})
            report_result = await self.generate_report(audit_run_id, self.settings)
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": "report", "result": self.compact_event_payload(report_result)},
            )
            await self.record_pipeline_summary(audit_run_id, {"steps": steps, "judge": judge_result, "report": report_result})
            await self.mark_audit_run_status(audit_run_id, "completed")
            await self.set_pipeline_state(audit_run_id, stage="completed", status="completed")
            await self.record_audit_run_event(audit_run_id, "pipeline_completed", {"report": self.compact_event_payload(report_result)})
            await self._cleanup_terminal_runtime(audit_run_id, terminal_status="completed", audit_run=audit_run)
        except PipelineCancelled as exc:
            await self.mark_audit_run_status(audit_run_id, "cancelled")
            await self.set_pipeline_state(audit_run_id, stage="cancelled", status="cancelled", error=str(exc))
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_cancelled",
                {"reason": str(exc), "steps": [self.compact_event_payload(step) for step in steps]},
            )
            await self._cleanup_terminal_runtime(audit_run_id, terminal_status="cancelled", audit_run=audit_run)
        except Exception as exc:
            if await self.is_cancel_requested(audit_run_id):
                reason = await self.cancel_reason(audit_run_id)
                await self.mark_audit_run_status(audit_run_id, "cancelled")
                await self.set_pipeline_state(audit_run_id, stage="cancelled", status="cancelled", error=reason or str(exc))
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_cancelled",
                    {
                        "reason": reason or str(exc),
                        "error": str(exc),
                        "steps": [self.compact_event_payload(step) for step in steps],
                    },
                )
                await self._cleanup_terminal_runtime(audit_run_id, terminal_status="cancelled", audit_run=audit_run)
                return
            await self.record_pipeline_event(audit_run_id, "pipeline_failed", {"error": str(exc), "steps": steps})
            await self.set_pipeline_state(audit_run_id, stage="failed", status="failed", error=str(exc))
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_failed",
                {"error": str(exc), "steps": [self.compact_event_payload(step) for step in steps]},
            )
            await self.mark_audit_run_status(audit_run_id, "failed")
            await self._cleanup_terminal_runtime(audit_run_id, terminal_status="failed", audit_run=audit_run)

    async def _cleanup_terminal_runtime(
        self,
        audit_run_id: str,
        *,
        terminal_status: str,
        audit_run: dict[str, Any],
    ) -> None:
        retain_on_failure = bool(audit_run.get("retain_runtime_on_failure"))
        if terminal_status == "failed" and retain_on_failure:
            await self.record_pipeline_event(
                audit_run_id,
                "runtime_cleanup_skipped",
                {"reason": "retain_runtime_on_failure", "terminal_status": terminal_status},
            )
            return
        cleanup = getattr(self.runtime, "cleanup_run", None)
        if cleanup is None:
            await self.record_pipeline_event(
                audit_run_id,
                "runtime_cleanup_skipped",
                {"reason": "runtime_cleanup_unavailable", "terminal_status": terminal_status},
            )
            return
        try:
            result = await cleanup(audit_run_id)
        except Exception as exc:
            await self.record_pipeline_event(
                audit_run_id,
                "runtime_cleanup_failed",
                {"error": str(exc), "terminal_status": terminal_status},
            )
            return
        await self.record_pipeline_event(
            audit_run_id,
            "runtime_cleanup_completed",
            {"terminal_status": terminal_status, "result": self.compact_event_payload(result)},
        )

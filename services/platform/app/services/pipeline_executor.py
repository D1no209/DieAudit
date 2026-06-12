from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.settings import Settings


class PipelineCancelled(RuntimeError):
    pass


AsyncCallback = Callable[..., Awaitable[Any]]


TEMPORAL_PIPELINE_STAGES = [
    "joern-cpg",
    "agent-audit",
    "code-analysis",
    "sca",
    "semgrep",
    "source-sink-analysis",
    "validators",
    "judgement",
    "poc-writing",
    "poc-verification",
    "report",
]
TEMPORAL_VALIDATOR_ATTEMPT_ACTIVITY = "dieaudit.validator_attempt"


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
        generate_pocs: AsyncCallback,
        verify_pocs: AsyncCallback,
        generate_report: AsyncCallback,
        compact_event_payload: Callable[[Any], Any],
        run_joern: AsyncCallback | None = None,
        run_code_batch_analysis: AsyncCallback | None = None,
        run_source_sink_analysis: AsyncCallback | None = None,
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
        self.run_joern = run_joern
        self.run_code_batch_analysis = run_code_batch_analysis
        self.run_source_sink_analysis = run_source_sink_analysis
        self.run_sca = run_sca
        self.run_semgrep = run_semgrep
        self.judge_audit_run = judge_audit_run
        self.generate_pocs = generate_pocs
        self.verify_pocs = verify_pocs
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
        initial_stage = "joern-cpg" if self._joern_enabled(audit_run) else "agent-audit"
        await self.record_audit_run_event(audit_run_id, "pipeline_started", {"stage": initial_stage})
        steps: list[dict[str, Any]] = []
        judge_result: dict[str, Any] = {}
        agent_external_network = self._agent_external_network(audit_run)
        try:
            await self.raise_if_cancelled(audit_run_id)
            if self._joern_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage="joern-cpg", status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "joern-cpg"})
                try:
                    if self.run_joern is None:
                        joern_result = {"ok": False, "available": False, "error": "Joern callback is not configured"}
                    else:
                        joern_result = await self.run_joern(
                            audit_run_id,
                            audit_run["project_id"],
                            workspace_path,
                            self.runtime,
                            audit_run,
                        )
                except Exception as exc:
                    joern_result = {"ok": False, "available": False, "error": str(exc)}
                    await self.record_pipeline_event(audit_run_id, "joern_failed", joern_result)
                steps.append({"step": "joern-cpg", "result": joern_result})
                if isinstance(audit_run.get("config"), dict):
                    audit_run["config"] = {**audit_run["config"], "joern_context": joern_result}
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "joern-cpg", "result": self.compact_event_payload(joern_result)},
                )
                if self._joern_required(audit_run) and not joern_result.get("ok"):
                    raise RuntimeError(str(joern_result.get("error") or joern_result.get("reason") or "Joern CPG build failed"))
                await self.raise_if_cancelled(audit_run_id)

            if self._agent_audit_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage="agent-audit", status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "agent-audit"})
                agent_input_payload = audit_run.get("config", {}).get("input_payload") or {
                    "goal": (
                        "Run a structured security audit pass. Return JSON with summary, findings, and evidence. "
                        "Every finding must include title, severity, file_path, line_start, description, confidence, and source."
                    )
                }
                if isinstance(agent_input_payload, dict):
                    joern_context = self._agent_joern_context(audit_run)
                    if joern_context["enabled"]:
                        agent_input_payload = {**agent_input_payload, "joern": joern_context}
                agent_result = await self.runtime.start_agent_run(
                    audit_run_id=audit_run_id,
                    project_id=audit_run["project_id"],
                    agent_name=audit_run.get("config", {}).get("agent_name") or "opencode-orchestrator",
                    workspace_host_path=workspace_path,
                    allow_external_network=agent_external_network,
                    retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
                    input_payload=agent_input_payload,
                )
                steps.append({"step": "agent-audit", "result": agent_result})
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "agent-audit", "result": self.compact_event_payload(agent_result)},
                )
                if self._agent_run_failed(agent_result):
                    raise RuntimeError(self._agent_run_error(agent_result) or "agent-audit failed")
                await self.raise_if_cancelled(audit_run_id)
            else:
                agent_result = self._skipped_result("orchestrator agent disabled")
                steps.append({"step": "agent-audit", "result": agent_result})
                await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": "agent-audit", "reason": agent_result["reason"]})

            if self._code_batch_analysis_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage="code-analysis", status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "code-analysis"})
                try:
                    if self.run_code_batch_analysis is None:
                        code_result = {"ok": False, "available": False, "error": "code batch analysis callback is not configured"}
                    else:
                        code_result = await self.run_code_batch_analysis(
                            audit_run_id,
                            audit_run["project_id"],
                            workspace_path,
                            self.runtime,
                            audit_run,
                        )
                except Exception as exc:
                    code_result = {"ok": False, "error": str(exc)}
                    await self.record_pipeline_event(audit_run_id, "code_analysis_failed", code_result)
                steps.append({"step": "code-analysis", "result": code_result})
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "code-analysis", "result": self.compact_event_payload(code_result)},
                )
                await self.raise_if_cancelled(audit_run_id)
            else:
                code_result = self._skipped_result("code-auditor agent disabled")
                steps.append({"step": "code-analysis", "result": code_result})
                await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": "code-analysis", "reason": code_result["reason"]})

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
            if self._source_sink_analysis_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage="source-sink-analysis", status="running")
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_started",
                    {"step": "source-sink-analysis", "finding_count": len(findings)},
                )
                try:
                    if self.run_source_sink_analysis is None:
                        source_sink_result = {"ok": False, "available": False, "error": "source-to-sink callback is not configured"}
                    else:
                        source_sink_result = await self.run_source_sink_analysis(
                            audit_run_id,
                            audit_run["project_id"],
                            workspace_path,
                            self.runtime,
                            audit_run,
                            findings,
                        )
                except Exception as exc:
                    source_sink_result = {"ok": False, "error": str(exc)}
                    await self.record_pipeline_event(audit_run_id, "source_sink_analysis_failed", source_sink_result)
                steps.append({"step": "source-sink-analysis", "result": source_sink_result})
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "source-sink-analysis", "result": self.compact_event_payload(source_sink_result)},
                )
                findings = await self.list_findings(audit_run_id)
                await self.raise_if_cancelled(audit_run_id)
            else:
                source_sink_result = self._skipped_result("source-sink-finder agent disabled")
                steps.append({"step": "source-sink-analysis", "result": source_sink_result})
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_skipped",
                    {"step": "source-sink-analysis", "reason": source_sink_result["reason"]},
                )

            if self._validators_enabled(audit_run):
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
                    validator_agent_name=self._config_str(audit_run, "validator_agent_name", "opencode-validator"),
                    allow_external_network=agent_external_network,
                    retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
                    wait_for_completion=True,
                    cancel_requested=lambda: self.is_cancel_requested(audit_run_id),
                    cancel_reason=lambda: self.cancel_reason(audit_run_id),
                )
                steps.append({"step": "validators", "result": validator_result})
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "validators", "result": self.compact_event_payload(validator_result)},
                )
                await self.raise_if_cancelled(audit_run_id)
            else:
                validator_result = self._skipped_result("validator agent disabled")
                steps.append({"step": "validators", "result": validator_result})
                await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": "validators", "reason": validator_result["reason"]})

            if self._judgement_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage="judgement", status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "judgement"})
                judge_result = await self.judge_audit_run(audit_run_id, self.runtime)
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "judgement", "result": self.compact_event_payload(judge_result)},
                )
                await self.raise_if_cancelled(audit_run_id)
            else:
                judge_result = self._skipped_result("judger agent disabled")
                steps.append({"step": "judgement", "result": judge_result})
                await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": "judgement", "reason": judge_result["reason"]})

            if self._poc_writing_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage="poc-writing", status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "poc-writing"})
                try:
                    poc_result = await self.generate_pocs(audit_run_id, self.runtime)
                except Exception as exc:
                    poc_result = {"ok": False, "error": str(exc)}
                    await self.record_pipeline_event(audit_run_id, "poc_writing_failed", poc_result)
                steps.append({"step": "poc-writing", "result": poc_result})
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "poc-writing", "result": self.compact_event_payload(poc_result)},
                )
                await self.raise_if_cancelled(audit_run_id)
            else:
                poc_result = self._skipped_result("poc-writer agent disabled")
                steps.append({"step": "poc-writing", "result": poc_result})
                await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": "poc-writing", "reason": poc_result["reason"]})

            if self._poc_verification_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage="poc-verification", status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "poc-verification"})
                try:
                    poc_verify_result = await self.verify_pocs(audit_run_id, self.runtime)
                except Exception as exc:
                    poc_verify_result = {"ok": False, "error": str(exc)}
                    await self.record_pipeline_event(audit_run_id, "poc_verification_failed", poc_verify_result)
                steps.append({"step": "poc-verification", "result": poc_verify_result})
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "poc-verification", "result": self.compact_event_payload(poc_verify_result)},
                )
                await self.raise_if_cancelled(audit_run_id)
            else:
                poc_verify_result = self._skipped_result("poc-verifier agent disabled")
                steps.append({"step": "poc-verification", "result": poc_verify_result})
                await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": "poc-verification", "reason": poc_verify_result["reason"]})

            await self.set_pipeline_state(audit_run_id, stage="report", status="running")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "report"})
            report_result = await self.generate_report(audit_run_id, self.settings)
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": "report", "result": self.compact_event_payload(report_result)},
            )
            result_quality = self._result_quality(steps=steps, judge_result=judge_result, report_result=report_result)
            final_status = "completed_with_warnings" if result_quality["warnings"] else "completed"
            final_event = "pipeline_completed_with_warnings" if final_status == "completed_with_warnings" else "pipeline_completed"
            await self.record_pipeline_summary(
                audit_run_id,
                {"steps": steps, "judge": judge_result, "report": report_result, "result_quality": result_quality},
            )
            await self.mark_audit_run_status(audit_run_id, final_status)
            await self.set_pipeline_state(audit_run_id, stage="completed", status=final_status)
            await self.record_audit_run_event(
                audit_run_id,
                final_event,
                {"report": self.compact_event_payload(report_result), "result_quality": self.compact_event_payload(result_quality)},
            )
            await self._cleanup_terminal_runtime(audit_run_id, terminal_status=final_status, audit_run=audit_run)
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

    async def prepare_temporal_pipeline(self, audit_run_id: str) -> dict[str, Any]:
        audit_run = await self.get_audit_run(audit_run_id)
        if not audit_run:
            raise RuntimeError(f"audit run not found: {audit_run_id}")
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        if not workspace_path:
            await self.mark_audit_run_status(audit_run_id, "failed")
            await self.set_pipeline_state(audit_run_id, stage="failed", status="failed", error="audit run has no workspace path")
            await self.record_audit_run_event(audit_run_id, "pipeline_failed", {"error": "audit run has no workspace path", "backend": "temporal"})
            await self._cleanup_terminal_runtime(audit_run_id, terminal_status="failed", audit_run=audit_run)
            raise RuntimeError("audit run has no workspace path")
        await self.mark_audit_run_status(audit_run_id, "running")
        initial_stage = "joern-cpg" if self._joern_enabled(audit_run) else "agent-audit"
        await self.record_audit_run_event(audit_run_id, "pipeline_started", {"stage": initial_stage, "backend": "temporal"})
        return {"audit_run_id": audit_run_id, "status": "running", "initial_stage": initial_stage, "stages": TEMPORAL_PIPELINE_STAGES}

    async def execute_temporal_stage(self, audit_run_id: str, stage: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
        audit_run = await self._audit_run_for_temporal_stage(audit_run_id, steps)
        workspace_path = audit_run.get("config", {}).get("workspace_host_path")
        if not workspace_path:
            raise RuntimeError("audit run has no workspace path")
        agent_external_network = self._agent_external_network(audit_run)
        await self.raise_if_cancelled(audit_run_id)

        if stage == "joern-cpg":
            if not self._joern_enabled(audit_run):
                return {"step": stage, "result": self._skipped_result("joern disabled"), "append_to_steps": False}
            await self.set_pipeline_state(audit_run_id, stage=stage, status="running")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": stage, "backend": "temporal"})
            try:
                if self.run_joern is None:
                    result = {"ok": False, "available": False, "error": "Joern callback is not configured"}
                else:
                    result = await self.run_joern(audit_run_id, audit_run["project_id"], workspace_path, self.runtime, audit_run)
            except Exception as exc:
                result = {"ok": False, "available": False, "error": str(exc)}
                await self.record_pipeline_event(audit_run_id, "joern_failed", result)
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": stage, "backend": "temporal", "result": self.compact_event_payload(result)},
            )
            if self._joern_required(audit_run) and not result.get("ok"):
                raise RuntimeError(str(result.get("error") or result.get("reason") or "Joern CPG build failed"))
            await self.raise_if_cancelled(audit_run_id)
            return {"step": stage, "result": result, "append_to_steps": True}

        if stage == "agent-audit":
            if self._agent_audit_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage=stage, status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": stage, "backend": "temporal"})
                agent_input_payload = audit_run.get("config", {}).get("input_payload") or {
                    "goal": (
                        "Run a structured security audit pass. Return JSON with summary, findings, and evidence. "
                        "Every finding must include title, severity, file_path, line_start, description, confidence, and source."
                    )
                }
                if isinstance(agent_input_payload, dict):
                    joern_context = self._agent_joern_context(audit_run)
                    if joern_context["enabled"]:
                        agent_input_payload = {**agent_input_payload, "joern": joern_context}
                result = await self.runtime.start_agent_run(
                    audit_run_id=audit_run_id,
                    project_id=audit_run["project_id"],
                    agent_name=audit_run.get("config", {}).get("agent_name") or "opencode-orchestrator",
                    workspace_host_path=workspace_path,
                    allow_external_network=agent_external_network,
                    retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
                    input_payload=agent_input_payload,
                )
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": stage, "backend": "temporal", "result": self.compact_event_payload(result)},
                )
                if self._agent_run_failed(result):
                    raise RuntimeError(self._agent_run_error(result) or "agent-audit failed")
                await self.raise_if_cancelled(audit_run_id)
                return {"step": stage, "result": result, "append_to_steps": True}
            result = self._skipped_result("orchestrator agent disabled")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": stage, "reason": result["reason"], "backend": "temporal"})
            return {"step": stage, "result": result, "append_to_steps": True}

        if stage == "code-analysis":
            if self._code_batch_analysis_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage=stage, status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": stage, "backend": "temporal"})
                try:
                    if self.run_code_batch_analysis is None:
                        result = {"ok": False, "available": False, "error": "code batch analysis callback is not configured"}
                    else:
                        result = await self.run_code_batch_analysis(audit_run_id, audit_run["project_id"], workspace_path, self.runtime, audit_run)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}
                    await self.record_pipeline_event(audit_run_id, "code_analysis_failed", result)
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": stage, "backend": "temporal", "result": self.compact_event_payload(result)},
                )
                await self.raise_if_cancelled(audit_run_id)
                return {"step": stage, "result": result, "append_to_steps": True}
            result = self._skipped_result("code-auditor agent disabled")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": stage, "reason": result["reason"], "backend": "temporal"})
            return {"step": stage, "result": result, "append_to_steps": True}

        if stage == "sca":
            await self.set_pipeline_state(audit_run_id, stage=stage, status="running")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": stage, "backend": "temporal"})
            try:
                result = await self.run_sca(audit_run_id, audit_run["project_id"], workspace_path, self.runtime, audit_run)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
                await self.record_pipeline_event(audit_run_id, "sca_failed", result)
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": stage, "backend": "temporal", "result": self.compact_event_payload(result)},
            )
            await self.raise_if_cancelled(audit_run_id)
            return {"step": stage, "result": result, "append_to_steps": True}

        if stage == "semgrep":
            await self.set_pipeline_state(audit_run_id, stage=stage, status="running")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": stage, "backend": "temporal"})
            try:
                result = await self.run_semgrep(audit_run_id, audit_run["project_id"], workspace_path, self.runtime, audit_run)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
                await self.record_pipeline_event(audit_run_id, "semgrep_failed", result)
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": stage, "backend": "temporal", "result": self.compact_event_payload(result)},
            )
            await self.raise_if_cancelled(audit_run_id)
            return {"step": stage, "result": result, "append_to_steps": True}

        if stage == "source-sink-analysis":
            findings = await self.list_findings(audit_run_id)
            if self._source_sink_analysis_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage=stage, status="running")
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_started",
                    {"step": stage, "finding_count": len(findings), "backend": "temporal"},
                )
                try:
                    if self.run_source_sink_analysis is None:
                        result = {"ok": False, "available": False, "error": "source-to-sink callback is not configured"}
                    else:
                        result = await self.run_source_sink_analysis(audit_run_id, audit_run["project_id"], workspace_path, self.runtime, audit_run, findings)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}
                    await self.record_pipeline_event(audit_run_id, "source_sink_analysis_failed", result)
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": stage, "backend": "temporal", "result": self.compact_event_payload(result)},
                )
                await self.raise_if_cancelled(audit_run_id)
                return {"step": stage, "result": result, "append_to_steps": True}
            result = self._skipped_result("source-sink-finder agent disabled")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": stage, "reason": result["reason"], "backend": "temporal"})
            return {"step": stage, "result": result, "append_to_steps": True}

        if stage == "validators":
            findings = await self.list_findings(audit_run_id)
            if self._validators_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage=stage, status="running")
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_started",
                    {"step": stage, "finding_count": len(findings), "validator_rounds": audit_run["validator_rounds"], "backend": "temporal"},
                )
                await self._prepare_temporal_validator_attempts(
                    audit_run_id=audit_run_id,
                    project_id=audit_run["project_id"],
                    findings=findings,
                    validator_rounds=audit_run["validator_rounds"],
                    max_parallel_validators=audit_run["max_parallel_validators"],
                    validator_agent_name=self._config_str(audit_run, "validator_agent_name", "opencode-validator"),
                    allow_external_network=agent_external_network,
                    retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
                )
                attempts = []
                for finding in findings:
                    for round_index in range(1, int(audit_run["validator_rounds"]) + 1):
                        attempts.append(
                            {
                                "audit_run_id": audit_run_id,
                                "project_id": audit_run["project_id"],
                                "finding": finding,
                                "workspace_host_path": workspace_path,
                                "round_index": round_index,
                                "validator_rounds": audit_run["validator_rounds"],
                                "validator_agent_name": self._config_str(audit_run, "validator_agent_name", "opencode-validator"),
                                "allow_external_network": agent_external_network,
                                "retain_runtime_on_failure": audit_run["retain_runtime_on_failure"],
                            }
                        )
                if not attempts:
                    result = {
                        "audit_run_id": audit_run_id,
                        "project_id": audit_run["project_id"],
                        "status": "accepted",
                        "scheduled": 0,
                        "validator_rounds": audit_run["validator_rounds"],
                        "max_parallel_validators": audit_run["max_parallel_validators"],
                        "validator_agent_name": self._config_str(audit_run, "validator_agent_name", "opencode-validator"),
                        "results": [],
                        "status_counts": {},
                        "note": "No findings were provided.",
                    }
                    await self.record_audit_run_event(
                        audit_run_id,
                        "pipeline_step_completed",
                        {"step": stage, "backend": "temporal", "result": self.compact_event_payload(result)},
                    )
                    return {"step": stage, "result": result, "append_to_steps": True}
                return {
                    "step": stage,
                    "append_to_steps": False,
                    "temporal_fanout": {
                        "kind": "validator-attempts",
                        "max_parallel": int(audit_run["max_parallel_validators"]),
                        "attempts": attempts,
                    },
                }
            result = self._skipped_result("validator agent disabled")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": stage, "reason": result["reason"], "backend": "temporal"})
            return {"step": stage, "result": result, "append_to_steps": True}

        if stage == "judgement":
            if self._judgement_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage=stage, status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": stage, "backend": "temporal"})
                result = await self.judge_audit_run(audit_run_id, self.runtime)
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": stage, "backend": "temporal", "result": self.compact_event_payload(result)},
                )
                await self.raise_if_cancelled(audit_run_id)
                return {"step": stage, "result": result, "judge_result": result, "append_to_steps": False}
            result = self._skipped_result("judger agent disabled")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": stage, "reason": result["reason"], "backend": "temporal"})
            return {"step": stage, "result": result, "judge_result": result, "append_to_steps": True}

        if stage == "poc-writing":
            if self._poc_writing_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage=stage, status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": stage, "backend": "temporal"})
                try:
                    result = await self.generate_pocs(audit_run_id, self.runtime)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}
                    await self.record_pipeline_event(audit_run_id, "poc_writing_failed", result)
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": stage, "backend": "temporal", "result": self.compact_event_payload(result)},
                )
                await self.raise_if_cancelled(audit_run_id)
                return {"step": stage, "result": result, "append_to_steps": True}
            result = self._skipped_result("poc-writer agent disabled")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": stage, "reason": result["reason"], "backend": "temporal"})
            return {"step": stage, "result": result, "append_to_steps": True}

        if stage == "poc-verification":
            if self._poc_verification_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage=stage, status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": stage, "backend": "temporal"})
                try:
                    result = await self.verify_pocs(audit_run_id, self.runtime)
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}
                    await self.record_pipeline_event(audit_run_id, "poc_verification_failed", result)
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": stage, "backend": "temporal", "result": self.compact_event_payload(result)},
                )
                await self.raise_if_cancelled(audit_run_id)
                return {"step": stage, "result": result, "append_to_steps": True}
            result = self._skipped_result("poc-verifier agent disabled")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": stage, "reason": result["reason"], "backend": "temporal"})
            return {"step": stage, "result": result, "append_to_steps": True}

        if stage == "report":
            await self.set_pipeline_state(audit_run_id, stage=stage, status="running")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": stage, "backend": "temporal"})
            result = await self.generate_report(audit_run_id, self.settings)
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": stage, "backend": "temporal", "result": self.compact_event_payload(result)},
            )
            return {"step": stage, "result": result, "report_result": result, "append_to_steps": False}

        raise RuntimeError(f"unknown temporal pipeline stage: {stage}")

    async def execute_temporal_validator_attempt(self, payload: dict[str, Any]) -> dict[str, Any]:
        audit_run_id = str(payload["audit_run_id"])
        await self.raise_if_cancelled(audit_run_id)
        result = await self.runtime.run_validator_attempt(
            audit_run_id=audit_run_id,
            project_id=str(payload["project_id"]),
            finding=dict(payload.get("finding") or {}),
            workspace_host_path=payload.get("workspace_host_path"),
            round_index=int(payload["round_index"]),
            validator_rounds=int(payload["validator_rounds"]),
            validator_agent_name=str(payload["validator_agent_name"]),
            allow_external_network=bool(payload.get("allow_external_network")),
            retain_runtime_on_failure=bool(payload.get("retain_runtime_on_failure")),
            cancel_requested=lambda: self.is_cancel_requested(audit_run_id),
            cancel_reason=lambda: self.cancel_reason(audit_run_id),
        )
        await self.raise_if_cancelled(audit_run_id)
        return result

    async def complete_temporal_validator_stage(
        self,
        audit_run_id: str,
        *,
        project_id: str,
        validator_rounds: int,
        max_parallel_validators: int,
        validator_agent_name: str,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        for result in results:
            status = str(result.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        summary = {
            "audit_run_id": audit_run_id,
            "project_id": project_id,
            "status": "accepted",
            "scheduled": len(results),
            "validator_rounds": validator_rounds,
            "max_parallel_validators": max_parallel_validators,
            "validator_agent_name": validator_agent_name,
            "results": results,
            "status_counts": status_counts,
            "temporal_fanout": True,
        }
        await self.record_audit_run_event(
            audit_run_id,
            "pipeline_step_completed",
            {"step": "validators", "backend": "temporal", "result": self.compact_event_payload(summary)},
        )
        await self.raise_if_cancelled(audit_run_id)
        return {"step": "validators", "result": summary, "append_to_steps": True}

    async def _prepare_temporal_validator_attempts(
        self,
        *,
        audit_run_id: str,
        project_id: str,
        findings: list[dict[str, Any]],
        validator_rounds: int,
        max_parallel_validators: int,
        validator_agent_name: str,
        allow_external_network: bool,
        retain_runtime_on_failure: bool,
    ) -> None:
        record_audit_run = getattr(self.runtime, "_record_audit_run", None)
        if record_audit_run is not None:
            await record_audit_run(
                audit_run_id=audit_run_id,
                project_id=project_id,
                validator_rounds=validator_rounds,
                max_parallel_validators=max_parallel_validators,
                allow_external_network=allow_external_network,
                retain_runtime_on_failure=retain_runtime_on_failure,
                config={"validator_agent_name": validator_agent_name, "finding_count": len(findings), "backend": "temporal"},
            )
        mark_findings_status = getattr(self.runtime, "_mark_findings_status", None)
        if mark_findings_status is not None:
            await mark_findings_status([str(finding.get("finding_id")) for finding in findings if finding.get("finding_id")], "validating")

    async def finalize_temporal_pipeline(
        self,
        audit_run_id: str,
        *,
        steps: list[dict[str, Any]],
        judge_result: dict[str, Any],
        report_result: dict[str, Any],
    ) -> dict[str, Any]:
        audit_run = await self._audit_run_for_temporal_stage(audit_run_id, steps)
        result_quality = self._result_quality(steps=steps, judge_result=judge_result, report_result=report_result)
        final_status = "completed_with_warnings" if result_quality["warnings"] else "completed"
        final_event = "pipeline_completed_with_warnings" if final_status == "completed_with_warnings" else "pipeline_completed"
        summary = {"steps": steps, "judge": judge_result, "report": report_result, "result_quality": result_quality}
        await self.record_pipeline_summary(audit_run_id, summary)
        await self.mark_audit_run_status(audit_run_id, final_status)
        await self.set_pipeline_state(audit_run_id, stage="completed", status=final_status)
        await self.record_audit_run_event(
            audit_run_id,
            final_event,
            {"report": self.compact_event_payload(report_result), "result_quality": self.compact_event_payload(result_quality), "backend": "temporal"},
        )
        await self._cleanup_terminal_runtime(audit_run_id, terminal_status=final_status, audit_run=audit_run)
        return {"audit_run_id": audit_run_id, "status": final_status, "summary": summary}

    async def fail_temporal_pipeline(
        self,
        audit_run_id: str,
        *,
        error: str,
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        audit_run = await self.get_audit_run(audit_run_id)
        if not audit_run:
            return {"audit_run_id": audit_run_id, "status": "failed", "error": error}
        if await self.is_cancel_requested(audit_run_id):
            reason = await self.cancel_reason(audit_run_id)
            await self.mark_audit_run_status(audit_run_id, "cancelled")
            await self.set_pipeline_state(audit_run_id, stage="cancelled", status="cancelled", error=reason or error)
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_cancelled",
                {"reason": reason or error, "error": error, "steps": [self.compact_event_payload(step) for step in steps], "backend": "temporal"},
            )
            await self._cleanup_terminal_runtime(audit_run_id, terminal_status="cancelled", audit_run=audit_run)
            return {"audit_run_id": audit_run_id, "status": "cancelled", "error": reason or error}
        await self.record_pipeline_event(audit_run_id, "pipeline_failed", {"error": error, "steps": steps, "backend": "temporal"})
        await self.set_pipeline_state(audit_run_id, stage="failed", status="failed", error=error)
        await self.record_audit_run_event(
            audit_run_id,
            "pipeline_failed",
            {"error": error, "steps": [self.compact_event_payload(step) for step in steps], "backend": "temporal"},
        )
        await self.mark_audit_run_status(audit_run_id, "failed")
        await self._cleanup_terminal_runtime(audit_run_id, terminal_status="failed", audit_run=audit_run)
        return {"audit_run_id": audit_run_id, "status": "failed", "error": error}

    async def _audit_run_for_temporal_stage(self, audit_run_id: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
        audit_run = await self.get_audit_run(audit_run_id)
        if not audit_run:
            raise RuntimeError(f"audit run not found: {audit_run_id}")
        config = dict(audit_run.get("config") or {})
        pipeline = dict(config.get("pipeline") or {})
        pipeline["steps"] = steps
        config["pipeline"] = pipeline
        joern_steps = [item for item in steps if isinstance(item, dict) and item.get("step") == "joern-cpg"]
        if joern_steps:
            joern_result = joern_steps[-1].get("result")
            if isinstance(joern_result, dict):
                config["joern_context"] = joern_result
        audit_run["config"] = config
        return audit_run

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

    @staticmethod
    def _result_quality(
        *,
        steps: list[dict[str, Any]],
        judge_result: dict[str, Any],
        report_result: dict[str, Any],
    ) -> dict[str, Any]:
        warnings: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {
            "agent_parse_warnings": 0,
            "tool_failures": 0,
            "validator_failures": 0,
            "unvalidated_findings": 0,
        }
        for step in steps:
            step_name = str(step.get("step") or "unknown")
            result = step.get("result")
            if not isinstance(result, dict):
                continue
            if step_name == "agent-audit":
                ingest = result.get("structured_ingest") if isinstance(result.get("structured_ingest"), dict) else {}
                parse_warnings = list(ingest.get("structured_parse_warnings") or ingest.get("warnings") or [])
                parse_status = str(ingest.get("structured_parse_status") or "")
                metrics["agent_parse_warnings"] += len(parse_warnings)
                if parse_status in {"not_found", "parsed_with_warnings"} or parse_warnings:
                    warnings.append(
                        {
                            "kind": "agent_structured_output",
                            "status": parse_status or "unknown",
                            "warnings": parse_warnings,
                        }
                    )
                if ingest and int(ingest.get("findings_created") or 0) == 0:
                    warnings.append({"kind": "agent_created_no_findings"})
            elif step_name == "joern-cpg":
                if result.get("ok") is False:
                    metrics["tool_failures"] += 1
                    warnings.append({"kind": "joern_cpg_failed", "result": result})
            elif step_name in {"sca", "semgrep"}:
                tool_status = str(result.get("status") or "")
                if result.get("ok") is False or result.get("available") is False or tool_status in {"syft_unavailable", "osv_unreachable", "unavailable", "failed"}:
                    metrics["tool_failures"] += 1
                    warnings.append({"kind": "tool_failure", "step": step_name, "result": result})
            elif step_name == "code-analysis":
                if result.get("ok") is False:
                    warnings.append({"kind": "code_batch_analysis_failed", "result": result})
                if result.get("skipped") and "disabled" in str(result.get("reason") or ""):
                    continue
                skipped = int(result.get("skipped") or 0)
                failed = int(result.get("failed") or 0)
                if skipped or failed:
                    warnings.append({"kind": "code_batch_analysis_incomplete", "skipped": skipped, "failed": failed})
            elif step_name == "source-sink-analysis":
                if result.get("ok") is False:
                    warnings.append({"kind": "source_sink_analysis_failed", "result": result})
                if result.get("skipped") and "disabled" not in str(result.get("reason") or ""):
                    warnings.append({"kind": "source_sink_analysis_skipped", "result": result})
            elif step_name == "validators":
                status_counts = result.get("status_counts") if isinstance(result.get("status_counts"), dict) else {}
                failed = int(status_counts.get("failed") or 0)
                cancelled = int(status_counts.get("cancelled") or 0)
                metrics["validator_failures"] += failed + cancelled
                if failed or cancelled:
                    warnings.append({"kind": "validator_attempt_failures", "status_counts": status_counts})
                if result.get("scheduled") == 0:
                    metrics["unvalidated_findings"] += 1
                    warnings.append({"kind": "no_validator_attempts_scheduled"})
            elif step_name == "poc-writing":
                if result.get("ok") is False:
                    warnings.append({"kind": "poc_writing_failed", "result": result})
                failed = int(result.get("failed") or 0)
                if failed:
                    warnings.append({"kind": "poc_writing_incomplete", "failed": failed})
            elif step_name == "poc-verification":
                if result.get("ok") is False:
                    warnings.append({"kind": "poc_verification_failed", "result": result})
                failed = int(result.get("failed") or 0)
                if failed:
                    warnings.append({"kind": "poc_verification_incomplete", "failed": failed})
        report_summary = report_result.get("summary") if isinstance(report_result, dict) else {}
        if isinstance(report_summary, dict):
            unvalidated = int(report_summary.get("unvalidated_findings") or 0)
            metrics["unvalidated_findings"] = max(metrics["unvalidated_findings"], unvalidated)
            if unvalidated:
                warnings.append({"kind": "unvalidated_findings", "count": unvalidated})
            for warning in report_summary.get("parse_warnings") or []:
                if isinstance(warning, dict):
                    warnings.append({"kind": "report_parse_warning", **warning})
        if isinstance(judge_result, dict):
            judger_agent = judge_result.get("agent_run")
            if isinstance(judger_agent, dict) and judger_agent.get("ok") is False:
                warnings.append({"kind": "judger_agent_failed", "result": judger_agent})
            judger_agents = judge_result.get("agent_runs")
            if isinstance(judger_agents, list):
                failed = [item for item in judger_agents if isinstance(item, dict) and str(item.get("status") or "").lower() == "failed"]
                if failed:
                    warnings.append({"kind": "judger_agent_failures", "count": len(failed), "results": failed})
        return {"status": "warn" if warnings else "pass", "warnings": warnings, "metrics": metrics}

    @staticmethod
    def _code_batch_analysis_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_code_batch_analysis", True)) and PipelineExecutor._agent_enabled(config, "code-auditor")

    @staticmethod
    def _source_sink_analysis_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_source_sink_analysis", True)) and PipelineExecutor._agent_enabled(config, "source-sink-finder")

    @staticmethod
    def _agent_audit_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return PipelineExecutor._agent_enabled(config, "orchestrator")

    @staticmethod
    def _validators_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_validators", True)) and PipelineExecutor._agent_enabled(config, "validator")

    @staticmethod
    def _judgement_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_judgement", True)) and PipelineExecutor._agent_enabled(config, "judger")

    @staticmethod
    def _poc_writing_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_poc_writing", True)) and PipelineExecutor._agent_enabled(config, "poc-writer")

    @staticmethod
    def _poc_verification_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_poc_verification", True)) and PipelineExecutor._agent_enabled(config, "poc-verifier")

    @staticmethod
    def _agent_enabled(config: dict[str, Any], agent: str) -> bool:
        enabled_agents = config.get("enabled_agents")
        if not isinstance(enabled_agents, list):
            return True
        return agent in {str(item) for item in enabled_agents}

    @staticmethod
    def _config_str(audit_run: dict[str, Any], key: str, default: str) -> str:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        value = config.get(key)
        return str(value) if value else default

    @staticmethod
    def _skipped_result(reason: str) -> dict[str, Any]:
        return {"ok": True, "skipped": True, "reason": reason}

    def _agent_external_network(self, audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("allow_agent_external_network", getattr(self.settings, "allow_agent_external_network", True)))

    @staticmethod
    def _agent_run_failed(agent_result: dict[str, Any]) -> bool:
        status = str(agent_result.get("opencode_status") or agent_result.get("status") or "").lower()
        return status == "failed" or bool(agent_result.get("error"))

    @staticmethod
    def _agent_run_error(agent_result: dict[str, Any]) -> str | None:
        if agent_result.get("error"):
            return str(agent_result["error"])
        result = agent_result.get("opencode_result")
        if isinstance(result, dict) and result.get("error"):
            return str(result["error"])
        return None

    @staticmethod
    def _joern_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_joern", True))

    @staticmethod
    def _joern_required(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("joern_required", True)) and not bool(config.get("allow_joern_unavailable", False))

    @classmethod
    def _agent_joern_context(cls, audit_run: dict[str, Any]) -> dict[str, Any]:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        result = config.get("joern_context") if isinstance(config.get("joern_context"), dict) else {}
        query_packs = config.get("joern_query_packs")
        if query_packs is None:
            query_packs = ["entrypoints", "authz", "injection", "file-io", "network", "secrets"]
        elif isinstance(query_packs, str):
            query_packs = [item.strip() for item in query_packs.split(",") if item.strip()]
        elif not isinstance(query_packs, list):
            query_packs = list(query_packs or [])
        return {
            "enabled": cls._joern_enabled(audit_run),
            "required": cls._joern_required(audit_run),
            "mcp": "joern-mcp",
            "cpg_path": result.get("cpg_path"),
            "cpg_artifact_id": result.get("artifact_id") or result.get("cpg_artifact_id"),
            "artifact_path": result.get("artifact_path"),
            "status": result.get("status"),
            "ok": result.get("ok"),
            "recommended_query_packs": query_packs,
        }

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
        generate_pocs: AsyncCallback,
        verify_pocs: AsyncCallback,
        generate_report: AsyncCallback,
        compact_event_payload: Callable[[Any], Any],
        list_evidence: AsyncCallback | None = None,
        run_structure_discovery: AsyncCallback | None = None,
        run_code_batch_analysis: AsyncCallback | None = None,
        run_source_sink_analysis: AsyncCallback | None = None,
        run_source_sink_finding: AsyncCallback | None = None,
        complete_source_sink_analysis: AsyncCallback | None = None,
        run_whiteboard_swarm: AsyncCallback | None = None,
        run_judger_finding: AsyncCallback | None = None,
        complete_judgement: AsyncCallback | None = None,
        run_poc_writer_finding: AsyncCallback | None = None,
        complete_poc_writing: AsyncCallback | None = None,
        run_poc_verifier_finding: AsyncCallback | None = None,
        complete_poc_verification: AsyncCallback | None = None,
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
        self.list_evidence = list_evidence
        self.run_structure_discovery = run_structure_discovery
        self.run_code_batch_analysis = run_code_batch_analysis
        self.run_source_sink_analysis = run_source_sink_analysis
        self.run_source_sink_finding = run_source_sink_finding
        self.complete_source_sink_analysis = complete_source_sink_analysis
        self.run_whiteboard_swarm = run_whiteboard_swarm
        self.run_judger_finding = run_judger_finding
        self.complete_judgement = complete_judgement
        self.run_poc_writer_finding = run_poc_writer_finding
        self.complete_poc_writing = complete_poc_writing
        self.run_poc_verifier_finding = run_poc_verifier_finding
        self.complete_poc_verification = complete_poc_verification
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
        await self.record_audit_run_event(audit_run_id, "pipeline_started", {"stage": "structure-discovery"})
        steps: list[dict[str, Any]] = []
        judge_result: dict[str, Any] = {}
        agent_external_network = self._agent_external_network(audit_run)
        try:
            await self.raise_if_cancelled(audit_run_id)
            if self._structure_discovery_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage="structure-discovery", status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "structure-discovery"})
                try:
                    if self.run_structure_discovery is None:
                        structure_result = {"ok": False, "available": False, "error": "structure discovery callback is not configured"}
                    else:
                        structure_result = await self.run_structure_discovery(
                            audit_run_id,
                            audit_run["project_id"],
                            workspace_path,
                            self.runtime,
                            audit_run,
                        )
                except Exception as exc:
                    structure_result = {"ok": False, "error": str(exc)}
                    await self.record_pipeline_event(audit_run_id, "structure_discovery_failed", structure_result)
                steps.append({"step": "structure-discovery", "result": structure_result})
                if isinstance(audit_run.get("config"), dict):
                    audit_run["config"] = {**audit_run["config"], "structure_context": structure_result}
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "structure-discovery", "result": self.compact_event_payload(structure_result)},
                )
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
                    agent_input_payload = {**agent_input_payload, "codebase_memory": self._agent_codebase_memory_context()}
                agent_result = await self.runtime.start_agent_run(
                    audit_run_id=audit_run_id,
                    project_id=audit_run["project_id"],
                    agent_name=audit_run.get("config", {}).get("agent_name") or "opencode-orchestrator",
                    workspace_host_path=workspace_path,
                    allow_external_network=agent_external_network,
                    retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
                    input_payload=agent_input_payload,
                )
                agent_step_result = agent_result
                steps.append({"step": "agent-audit", "result": agent_step_result})
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "agent-audit", "result": self.compact_event_payload(agent_step_result)},
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

            await self.set_pipeline_state(audit_run_id, stage="value-triage", status="running")
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_started",
                {
                    "step": "value-triage",
                    "policy": (
                        "Main-agent value triage runs before whiteboard swarm so standalone hygiene findings "
                        "do not trigger deeper agent work."
                    ),
                },
            )
            triage_result = {
                "ok": True,
                "mode": "pre-swarm",
                "policy": "exclude standalone low-impact hygiene findings from swarm scheduling",
            }
            steps.append({"step": "value-triage", "result": triage_result})
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": "value-triage", "result": triage_result},
            )
            await self.raise_if_cancelled(audit_run_id)

            if self._whiteboard_swarm_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage="whiteboard-swarm", status="running")
                await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "whiteboard-swarm"})
                try:
                    if self.run_whiteboard_swarm is None:
                        whiteboard_result = {"ok": False, "available": False, "error": "whiteboard swarm callback is not configured"}
                    else:
                        whiteboard_result = await self.run_whiteboard_swarm(audit_run_id, self.runtime)
                except Exception as exc:
                    whiteboard_result = {"ok": False, "error": str(exc)}
                    await self.record_pipeline_event(audit_run_id, "whiteboard_swarm_failed", whiteboard_result)
                steps.append({"step": "whiteboard-swarm", "result": whiteboard_result})
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "whiteboard-swarm", "result": self.compact_event_payload(whiteboard_result)},
                )
                await self.raise_if_cancelled(audit_run_id)
            else:
                whiteboard_result = self._skipped_result("whiteboard swarm disabled")
                steps.append({"step": "whiteboard-swarm", "result": whiteboard_result})
                await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": "whiteboard-swarm", "reason": whiteboard_result["reason"]})

            findings = await self.list_findings(audit_run_id)
            if self._validation_judgement_enabled(audit_run):
                await self.set_pipeline_state(audit_run_id, stage="validation-judgement", status="running")
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_started",
                    {"step": "validation-judgement", "finding_count": len(findings), "validator_rounds": audit_run["validator_rounds"]},
                )
                validator_result = await self.runtime.scale_validators(
                    audit_run_id=audit_run_id,
                    project_id=audit_run["project_id"],
                    findings=findings,
                    workspace_host_path=workspace_path,
                    validator_rounds=audit_run["validator_rounds"],
                    max_parallel_validators=audit_run["max_parallel_validators"],
                    validator_agent_name=self._config_str(audit_run, "validation_judgement_agent_name", self._config_str(audit_run, "validator_agent_name", "opencode-validator")),
                    allow_external_network=agent_external_network,
                    retain_runtime_on_failure=audit_run["retain_runtime_on_failure"],
                    wait_for_completion=True,
                    cancel_requested=lambda: self.is_cancel_requested(audit_run_id),
                    cancel_reason=lambda: self.cancel_reason(audit_run_id),
                )
                judge_result = {"validation_judgement": validator_result}
                steps.append({"step": "validation-judgement", "result": validator_result})
                await self.record_audit_run_event(
                    audit_run_id,
                    "pipeline_step_completed",
                    {"step": "validation-judgement", "result": self.compact_event_payload(validator_result)},
                )
                await self.raise_if_cancelled(audit_run_id)
            else:
                validator_result = self._skipped_result("validation-judgement disabled")
                judge_result = validator_result
                steps.append({"step": "validation-judgement", "result": validator_result})
                await self.record_audit_run_event(audit_run_id, "pipeline_step_skipped", {"step": "validation-judgement", "reason": validator_result["reason"]})

            await self.set_pipeline_state(audit_run_id, stage="feedback-loop", status="running")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "feedback-loop"})
            feedback_result = await self._run_feedback_loop(
                audit_run_id=audit_run_id,
                audit_run=audit_run,
                workspace_path=workspace_path,
                validation_result=validator_result,
            )
            steps.append({"step": "feedback-loop", "result": feedback_result})
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": "feedback-loop", "result": self.compact_event_payload(feedback_result)},
            )
            await self.raise_if_cancelled(audit_run_id)

            if self._legacy_judgement_enabled(audit_run):
                await self.record_pipeline_event(audit_run_id, "legacy_judgement_skipped", {"reason": "validation-judgement replaces judgement"})
            if self._legacy_source_sink_analysis_enabled(audit_run):
                await self.record_pipeline_event(audit_run_id, "legacy_source_sink_skipped", {"reason": "whiteboard-swarm replaces source-sink-analysis"})

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

    async def _run_feedback_loop(
        self,
        *,
        audit_run_id: str,
        audit_run: dict[str, Any],
        workspace_path: str,
        validation_result: dict[str, Any],
    ) -> dict[str, Any]:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        if not bool(config.get("enable_feedback_loop", True)):
            return self._skipped_result("feedback loop disabled")
        if self.run_code_batch_analysis is None or not self._code_batch_analysis_enabled(audit_run):
            return self._skipped_result("code batch analysis unavailable")
        max_rounds = max(0, int(config.get("max_feedback_rounds") or 2))
        if max_rounds <= 0:
            return self._skipped_result("max feedback rounds is zero")
        status_counts = validation_result.get("status_counts") if isinstance(validation_result.get("status_counts"), dict) else {}
        decisions = validation_result.get("decisions") if isinstance(validation_result.get("decisions"), list) else []
        confirmed = int(status_counts.get("confirmed") or status_counts.get("pass") or status_counts.get("completed_confirmed") or 0)
        needs_review = int(status_counts.get("needs_review") or 0)
        false_positive = int(status_counts.get("false_positive") or status_counts.get("failed") or 0)
        if not decisions and not status_counts:
            return {"ok": True, "skipped": True, "reason": "no validation status available"}
        if confirmed or needs_review:
            return {"ok": True, "skipped": True, "reason": "confirmed or needs_review findings exist", "status_counts": status_counts}
        if false_positive <= 0 and status_counts:
            return {"ok": True, "skipped": True, "reason": "validation did not indicate all candidates are unreachable", "status_counts": status_counts}
        results = []
        feedback = {
            "round_reason": "all candidates were rejected or unreachable",
            "validation_status_counts": status_counts,
            "validation_decisions": decisions[:50],
            "guidance": [
                "Avoid repeating candidates already marked false_positive or unreachable.",
                "Search uncovered architecture modules, critical flows, codebase-memory graph paths, and dependency-enabled code paths.",
                "Prefer new candidate_vulnerability Whiteboard cards with concrete files, lines, source, sink, and reachability questions.",
            ],
        }
        for round_index in range(1, max_rounds + 1):
            feedback_config = dict(config)
            feedback_config["feedback_loop"] = {**feedback, "round_index": round_index, "max_rounds": max_rounds}
            feedback_audit_run = {**audit_run, "config": feedback_config}
            try:
                result = await self.run_code_batch_analysis(
                    audit_run_id,
                    audit_run["project_id"],
                    workspace_path,
                    self.runtime,
                    feedback_audit_run,
                )
            except Exception as exc:
                result = {"ok": False, "round_index": round_index, "error": str(exc)}
                await self.record_pipeline_event(audit_run_id, "feedback_loop_failed", result)
                results.append(result)
                break
            result = {**result, "round_index": round_index}
            results.append(result)
            await self.record_pipeline_event(audit_run_id, "feedback_loop_round_completed", result)
            created = int(result.get("findings_created") or result.get("cards_created") or result.get("candidates_created") or 0)
            if created <= 0:
                break
        return {
            "ok": all(bool(item.get("ok", True)) for item in results),
            "rounds": len(results),
            "max_rounds": max_rounds,
            "results": results,
            "feedback": feedback,
        }

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
            elif step_name == "whiteboard-swarm":
                if result.get("ok") is False:
                    warnings.append({"kind": "whiteboard_swarm_failed", "result": result})
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
        return False

    @staticmethod
    def _legacy_source_sink_analysis_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_source_sink_analysis", False)) and PipelineExecutor._agent_enabled(config, "source-sink-finder")

    @staticmethod
    def _whiteboard_swarm_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_whiteboard", True)) and bool(config.get("enable_whiteboard_swarm", True))

    @staticmethod
    def _structure_discovery_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_structure_discovery", True))

    @staticmethod
    def _agent_audit_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return PipelineExecutor._agent_enabled(config, "orchestrator")

    @staticmethod
    def _validators_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return PipelineExecutor._validation_judgement_enabled(audit_run)

    @staticmethod
    def _validation_judgement_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_validation_judgement", True)) and (
            PipelineExecutor._agent_enabled(config, "validation-judgement") or PipelineExecutor._agent_enabled(config, "validator")
        )

    @staticmethod
    def _judgement_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return False

    @staticmethod
    def _legacy_judgement_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_judgement", False)) and PipelineExecutor._agent_enabled(config, "judger")

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
    @staticmethod
    def _agent_codebase_memory_context() -> dict[str, Any]:
        return {
            "mcp": "codebase-memory-mcp",
            "repo_path": "/workspace",
            "cache_dir": "/artifacts/codebase-memory",
            "instruction": (
                "Call index_repository for /workspace when graph context is needed or missing. "
                "Use get_architecture before broad planning, then search_graph, trace_path, query_graph, "
                "get_code_snippet, detect_changes, and search_code for focused security analysis."
            ),
        }

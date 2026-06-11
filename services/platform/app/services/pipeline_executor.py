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
            agent_external_network = self._agent_external_network(audit_run)
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

            await self.set_pipeline_state(audit_run_id, stage="judgement", status="running")
            await self.record_audit_run_event(audit_run_id, "pipeline_step_started", {"step": "judgement"})
            judge_result = await self.judge_audit_run(audit_run_id, self.runtime)
            await self.record_audit_run_event(
                audit_run_id,
                "pipeline_step_completed",
                {"step": "judgement", "result": self.compact_event_payload(judge_result)},
            )
            await self.raise_if_cancelled(audit_run_id)

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
                skipped = int(result.get("skipped") or 0)
                failed = int(result.get("failed") or 0)
                if skipped or failed:
                    warnings.append({"kind": "code_batch_analysis_incomplete", "skipped": skipped, "failed": failed})
            elif step_name == "source-sink-analysis":
                if result.get("ok") is False:
                    warnings.append({"kind": "source_sink_analysis_failed", "result": result})
                if result.get("skipped"):
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
        return bool(config.get("enable_code_batch_analysis", True))

    @staticmethod
    def _source_sink_analysis_enabled(audit_run: dict[str, Any]) -> bool:
        config = audit_run.get("config") if isinstance(audit_run.get("config"), dict) else {}
        return bool(config.get("enable_source_sink_analysis", True))

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

from __future__ import annotations

from types import SimpleNamespace

from app.api import routes
from app.api.routes import (
    _copy_finding_agent_artifact,
    _ensure_finding_state_markdown,
    _finding_agent_source_artifacts,
    _finding_artifact_contract,
    _finding_report_markdown,
    _report_markdown,
    _report_summary,
)
from app.services.artifacts import ArtifactStore


def test_report_summary_exposes_quality_gaps() -> None:
    findings = [
        {
            "finding_id": "finding-1",
            "status": "candidate",
            "severity": "high",
            "title": "Missing auth",
            "source": "agent",
            "description": "route lacks auth",
        },
        {
            "finding_id": "finding-2",
            "status": "needs_review",
            "severity": "medium",
            "title": "Weak crypto",
            "source": "semgrep",
            "description": "weak hash",
        },
    ]
    attempts = [
        {
            "attempt_id": "attempt-1",
            "finding_id": "finding-2",
            "round_index": 1,
            "status": "failed",
            "agent_run_id": "agent-2",
            "result": {"error": "validator crashed"},
        }
    ]
    agent_runs = [
        {
            "agent_run_id": "agent-1",
            "agent_name": "opencode-orchestrator",
            "output_summary": {
                "structured_ingest": {
                    "structured_parse_status": "parsed_with_warnings",
                    "structured_parse_warnings": [{"kind": "finding_missing_fields"}],
                }
            },
        }
    ]
    audit_events = [
        {"event_type": "semgrep_failed", "payload": {"ok": False, "error": "semgrep unavailable"}},
    ]

    summary = _report_summary(
        findings=findings,
        evidence=[
            {"kind": "source-sink-chain", "finding_id": "finding-1"},
            {"kind": "poc-artifact", "finding_id": "finding-1"},
            {"kind": "poc-verification", "finding_id": "finding-1"},
        ],
        attempts=attempts,
        agent_runs=agent_runs,
        audit_events=audit_events,
        dependencies=[
            {"ecosystem": "npm", "vulnerability_count": 2},
            {"ecosystem": "PyPI", "vulnerability_count": 0},
        ],
    )

    assert summary["finding_count_by_status"] == {"candidate": 1, "needs_review": 1}
    assert summary["source_sink_chain_count"] == 1
    assert summary["poc_artifact_count"] == 1
    assert summary["poc_verification_count"] == 1
    assert summary["validation_attempt_count_by_status"] == {"failed": 1}
    assert summary["parse_warning_count"] == 1
    assert summary["tool_failure_count"] == 1
    assert summary["validator_failure_count"] == 1
    assert summary["unvalidated_findings"] == 1
    assert summary["unvalidated_finding_ids"] == ["finding-1"]
    assert summary["dependency_coverage"] == {
        "dependency_count": 2,
        "vulnerable_package_count": 1,
        "vulnerability_count": 2,
        "by_ecosystem": {"PyPI": 1, "npm": 1},
        "sca_events": [],
    }


def test_report_markdown_includes_quality_sections() -> None:
    payload = {
        "audit_run": {"audit_run_id": "run-1", "project_id": "project-1", "snapshot_id": None, "status": "completed_with_warnings"},
        "summary": {
            "parse_warning_count": 1,
            "tool_failure_count": 1,
            "validator_failure_count": 1,
            "unvalidated_findings": 1,
            "source_sink_chain_count": 1,
            "poc_artifact_count": 1,
            "poc_verification_count": 1,
            "finding_report_count": 1,
            "finding_count_by_status": {"needs_review": 1},
            "validation_attempt_count_by_status": {"failed": 1},
            "parse_warnings": [{"agent_run_id": "agent-1", "status": "parsed_with_warnings"}],
            "tool_failures": [{"event_type": "semgrep_failed"}],
            "validator_failures": [{"finding_id": "finding-1", "round_index": 1, "status": "failed"}],
            "unvalidated_finding_ids": ["finding-1"],
            "dependency_coverage": {
                "dependency_count": 2,
                "vulnerable_package_count": 1,
                "vulnerability_count": 2,
                "by_ecosystem": {"npm": 2},
            },
        },
        "findings": [
            {
                "finding_id": "finding-1",
                "title": "Missing auth",
                "severity": "high",
                "status": "needs_review",
                "file_path": "src/app.py",
                "line_start": 42,
                "source": "agent",
                "description": "route lacks auth",
            }
        ],
        "validation_attempts": [],
        "evidence": [],
    }

    markdown = _report_markdown(payload)

    assert "## Result Quality" in markdown
    assert "### Tool Failures" in markdown
    assert "### Unvalidated Findings" in markdown
    assert "### Dependency Coverage" in markdown
    assert "PoC artifacts" in markdown
    assert "Source-to-sink chains" in markdown
    assert "completed_with_warnings" in markdown


def test_finding_report_markdown_is_finding_scoped() -> None:
    markdown = _finding_report_markdown(
        {
            "finding": {
                "finding_id": "finding-1",
                "title": "SQL injection",
                "severity": "high",
                "status": "confirmed",
                "file_path": "src/app.py",
                "line_start": 42,
                "source": "source-sink-finder",
                "description": "tainted request parameter reaches SQL sink",
                "finding_markdown": {
                    "artifact_id": "finding-md-1",
                    "relative_path": "findings/run-1/finding-1/finding.md",
                    "artifact_uri": "local://artifacts/findings/run-1/finding-1/finding.md",
                    "exists": True,
                },
            },
            "evidence": [
                {
                    "kind": "source-sink-chain",
                    "summary": "request.args reaches db.execute",
                    "artifact": {"artifact_id": "artifact-1"},
                    "payload": {},
                },
                {
                    "kind": "judger-agent-report",
                    "summary": "Judger Report",
                    "artifact": {"artifact_id": "judger-report-1"},
                    "payload": {
                        "report_source": "agent-written",
                        "agent_result_artifact_id": "judger-result-1",
                    },
                },
                {"kind": "poc-artifact", "summary": "curl reproducer", "payload": {"artifact_id": "poc-1"}},
            ],
            "validation_attempts": [
                {"round_index": 1, "status": "completed", "agent_run_id": "validator-1"},
            ],
            "agent_runs": [
                {"agent_name": "opencode-source-sink-finder", "agent_run_id": "agent-1", "status": "completed"},
            ],
        }
    )

    assert "Finding Report: SQL injection" in markdown
    assert "Tracking Markdown" in markdown
    assert "finding-md-1" in markdown
    assert "source-sink-chain" in markdown
    assert "agent-written" in markdown
    assert "judger-result-1" in markdown
    assert "poc-artifact" in markdown
    assert "opencode-source-sink-finder" in markdown
    assert "validator-1" in markdown


def test_report_summary_ignores_missing_json_when_markdown_handoff_exists() -> None:
    summary = _report_summary(
        findings=[{"finding_id": "finding-1", "status": "confirmed"}],
        evidence=[
            {
                "kind": "poc-writer-agent-report",
                "finding_id": "finding-1",
                "payload": {
                    "agent_run_id": "agent-1",
                    "finding_markdown": {"artifact_id": "finding-md-1"},
                },
            }
        ],
        attempts=[],
        agent_runs=[
            {
                "agent_run_id": "agent-1",
                "agent_name": "opencode-poc-writer",
                "output_summary": {
                    "structured_ingest": {
                        "structured_parse_status": "not_found",
                        "structured_parse_warnings": [{"kind": "structured_output_not_found"}],
                    }
                },
            }
        ],
        audit_events=[],
    )

    assert summary["parse_warning_count"] == 0
    assert summary["parse_warnings"] == []


def test_finding_artifact_contract_uses_independent_finding_directory() -> None:
    contract = _finding_artifact_contract("run-1", "finding-1", "source-sink")

    assert contract["finding_directory"] == "findings/run-1/finding-1"
    assert contract["finding_markdown_path"] == "/finding/finding.md"
    assert contract["canonical_finding_markdown"] == "findings/run-1/finding-1/finding.md"
    assert contract["agent_writable_report_path"] == "/artifacts/source-sink-report.md"
    assert contract["platform_canonical_directory"] == "findings/run-1/finding-1/agent-reports"


def test_finding_state_markdown_initializes_shared_agent_workspace(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(artifact_root=tmp_path))

    path = _ensure_finding_state_markdown(
        "run-1",
        {
            "finding_id": "finding-1",
            "title": "Path traversal",
            "severity": "high",
            "status": "candidate",
            "source": "semgrep",
            "rule_id": "path-traversal",
            "file_path": "app.py",
            "line_start": 8,
            "description": "request parameter reaches open",
        },
        evidence=[{"kind": "semgrep-result", "summary": "open(path)"}],
        attempts=[],
    )

    assert path == tmp_path / "findings" / "run-1" / "finding-1" / "finding.md"
    text = path.read_text(encoding="utf-8")
    assert "Path traversal" in text
    assert "Each Agent must read this file" in text
    assert (path.parent / "agent-reports").is_dir()
    assert (path.parent / "poc").is_dir()


def test_finding_agent_source_artifacts_resolve_agent_written_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(artifact_root=tmp_path))
    source_dir = tmp_path / "agent-runs" / "run-1" / "agent-1"
    source_dir.mkdir(parents=True)
    report_path = source_dir / "source-sink-report.md"
    result_path = source_dir / "source-sink-result.json"
    report_path.write_text("# agent report", encoding="utf-8")
    result_path.write_text('{"chains":[]}', encoding="utf-8")

    source = _finding_agent_source_artifacts("run-1", "agent-1", "source-sink")

    assert source["report_path"] == report_path
    assert source["json_path"] == result_path


def test_copy_finding_agent_artifact_preserves_agent_content_under_finding_directory(tmp_path) -> None:
    settings = SimpleNamespace(artifact_root=tmp_path, artifact_storage_backend="local")
    source_path = tmp_path / "agent-runs" / "run-1" / "agent-1" / "judger-report.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("# original judger report\n\nAgent-written content.", encoding="utf-8")

    metadata = _copy_finding_agent_artifact(
        store=ArtifactStore(settings),
        source_path=source_path,
        destination_relative_path="findings/run-1/finding-1/agent-reports/judger-agent-1.md",
        content_type="text/markdown; charset=utf-8",
    )

    copied = tmp_path / "findings" / "run-1" / "finding-1" / "agent-reports" / "judger-agent-1.md"
    assert copied.read_text(encoding="utf-8") == "# original judger report\n\nAgent-written content."
    assert metadata["relative_path"] == "findings/run-1/finding-1/agent-reports/judger-agent-1.md"

from __future__ import annotations

from app.api.routes import _report_markdown, _report_summary


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
        evidence=[],
        attempts=attempts,
        agent_runs=agent_runs,
        audit_events=audit_events,
        dependencies=[
            {"ecosystem": "npm", "vulnerability_count": 2},
            {"ecosystem": "PyPI", "vulnerability_count": 0},
        ],
    )

    assert summary["finding_count_by_status"] == {"candidate": 1, "needs_review": 1}
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
    assert "completed_with_warnings" in markdown

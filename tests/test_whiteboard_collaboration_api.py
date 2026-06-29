from __future__ import annotations

from pathlib import Path

from app.api.routes import _swarm_candidate_value_decision
from app.domain.models import WhiteboardCard


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_whiteboard_collaboration_routes_are_exposed() -> None:
    routes = read_source("services/platform/app/api/routes.py")
    schemas = read_source("services/platform/app/schemas/runtime.py")

    assert '"/audit-runs/{audit_run_id}/whiteboard/events"' in routes
    assert '"/audit-runs/{audit_run_id}/whiteboard/subscriptions"' in routes
    assert '"/audit-runs/{audit_run_id}/whiteboard/notifications"' in routes
    assert '"/audit-runs/{audit_run_id}/whiteboard/schedule-requests"' in routes
    assert '"/audit-runs/{audit_run_id}/whiteboard/agent-graph"' in routes
    assert "CreateWhiteboardSubscriptionRequest" in schemas
    assert "CreateWhiteboardScheduleRequest" in schemas


def test_whiteboard_mcp_exposes_listener_tools() -> None:
    mcp = read_source("services/mcp-tools/tool_mcp.py")
    template = read_source("configs/mcp-templates/whiteboard-mcp.yaml")

    for tool_name in [
        "subscribe_changes",
        "list_notifications",
        "mark_notification",
        "request_agent_help",
        "read_structure",
    ]:
        assert tool_name in mcp
        assert tool_name in template


def test_pipeline_exposes_structure_discovery_stage() -> None:
    executor = read_source("services/platform/app/services/pipeline_executor.py")
    routes = read_source("services/platform/app/api/routes.py")
    worker = read_source("services/platform/app/worker.py")

    assert "structure-discovery" in executor
    assert "_run_structure_discovery" in routes
    assert "run_structure_discovery=_run_structure_discovery" in worker


def test_swarm_uses_value_triage_before_scheduling_agents() -> None:
    executor = read_source("services/platform/app/services/pipeline_executor.py")
    routes = read_source("services/platform/app/api/routes.py")
    whiteboard = read_source("services/platform/app/services/whiteboard.py")

    assert "value-triage" in executor
    assert "_triage_whiteboard_swarm_candidates" in routes
    assert "eligible_card_ids" in routes
    assert "excluded_card_ids" in routes
    assert "low_value_swarm_triage" in whiteboard
    assert "All related cards were triaged as low-value" in whiteboard


def test_runtime_exposes_inactive_agent_cleanup_route() -> None:
    routes = read_source("services/platform/app/api/routes.py")
    orchestrator = read_source("services/platform/app/runtime/orchestrator.py")

    assert '"/audit-runs/{audit_run_id}/cleanup-inactive-runtime"' in routes
    assert "cleanup_inactive_agent_runtime" in orchestrator


def test_agent_runtime_and_deliverable_interfaces_are_exposed() -> None:
    routes = read_source("services/platform/app/api/routes.py")
    schemas = read_source("services/platform/app/schemas/runtime.py")
    models = read_source("services/platform/app/domain/models.py")

    assert '"/audit-runs/{audit_run_id}/agent-runtimes/ensure"' in routes
    assert '"/internal/agent-runs/{agent_run_id}/transcript-events"' in routes
    assert '"/audit-runs/{audit_run_id}/agent-runs/{agent_run_id}/transcript-events"' in routes
    assert '"/audit-runs/{audit_run_id}/cleanup-runtime"' in routes
    assert '"/audit-runs/{audit_run_id}/deliverables"' in routes
    assert "EnsureAgentRuntimeRequest" in schemas
    assert "AgentTranscriptEventsRequest" in schemas
    assert "class AgentRuntime" in models
    assert "class AgentTranscriptEvent" in models
    assert "class FindingTriageDecision" in models
    assert "class DeliverableArtifact" in models


def test_swarm_value_triage_downgrades_hygiene_and_keeps_exploitable_findings() -> None:
    ssl_card = WhiteboardCard(
        card_id="card-ssl",
        audit_run_id="run-1",
        project_id="project-1",
        title="SSL/TLS Verification Disabled in HTTP Clients",
        card_type="candidate_vulnerability",
        status="open",
        content="curl disables certificate verification.",
        metadata_json={"severity": "high"},
    )
    upload_card = WhiteboardCard(
        card_id="card-upload",
        audit_run_id="run-1",
        project_id="project-1",
        title="File Upload RCE through user-controlled extension",
        card_type="candidate_vulnerability",
        status="open",
        content="Chunk upload lets attacker write a PHP webshell under public storage.",
        metadata_json={"severity": "high"},
    )

    assert _swarm_candidate_value_decision(ssl_card)["decision"] == "appendix_only"
    assert _swarm_candidate_value_decision(upload_card)["decision"] == "deep_dive"

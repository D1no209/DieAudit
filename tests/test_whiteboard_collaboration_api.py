from __future__ import annotations

from pathlib import Path


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

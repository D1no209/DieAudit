from __future__ import annotations

from pathlib import Path

from app.api.routes import _execution_graph_summary


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_execution_graph_route_is_exposed() -> None:
    routes = read_source("services/platform/app/api/routes.py")
    api = read_source("services/web-ui/src/client/dashboardApi.ts")
    types = read_source("services/web-ui/src/types.ts")

    assert '"/audit-runs/{audit_run_id}/execution-graph"' in routes
    assert "def _execution_graph(" in routes
    assert "readJson<ExecutionGraph>" in api
    assert "ExecutionGraphNode" in types
    assert "ExecutionGraphEdge" in types


def test_execution_graph_summary_counts_completed_unfinished_and_failed() -> None:
    summary = _execution_graph_summary(
        [
            {"kind": "audit-run", "status": "running"},
            {"kind": "agent-run", "status": "completed"},
            {"kind": "agent-run", "status": "failed"},
            {"kind": "whiteboard-task", "status": "queued"},
            {"kind": "container", "status": "completed"},
        ]
    )

    assert summary["node_count"] == 5
    assert summary["by_kind"]["agent-run"] == 2
    assert summary["completed"] == 2
    assert summary["unfinished"] == 2
    assert summary["failed"] == 1


def test_agent_runs_page_surfaces_execution_graph() -> None:
    page = read_source("services/web-ui/src/pages/AgentRunsPage.tsx")
    renderers = read_source("services/web-ui/src/routes/routeRenderers.tsx")
    refresh = read_source("services/web-ui/src/hooks/dashboard/useDashboardRefresh.ts")

    assert "Execution Graph" in page
    assert "agent-graph" in page
    assert "onOpenAgentEvents" in page
    assert "onOpenContainerLogs" in page
    assert "executionGraph={state.executionGraph}" in renderers
    assert "setExecutionGraph(bundle.executionGraph)" in refresh

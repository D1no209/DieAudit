from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_audit_result_surfaces_have_dedicated_routes() -> None:
    navigation = read_source("services/web-ui/src/navigation.tsx")
    routes = read_source("services/web-ui/src/routes/AppRoutes.tsx")

    for view in ("agent-runs", "dependencies", "reports"):
        assert f'"{view}"' in navigation
        assert f'activeView === "{view}"' in routes


def test_audit_runs_page_does_not_embed_result_tables() -> None:
    audit_runs_page = read_source("services/web-ui/src/pages/AuditRunsPage.tsx")

    assert "AgentRunsPage" not in audit_runs_page
    assert "ReportsPage" not in audit_runs_page
    assert "Tabs" not in audit_runs_page


def test_findings_page_does_not_embed_dependency_inventory() -> None:
    findings_page = read_source("services/web-ui/src/pages/FindingsPage.tsx")

    assert "DependencyInventory" not in findings_page
    assert "DependenciesPage" not in findings_page
    assert "Tabs" not in findings_page

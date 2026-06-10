from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_audit_result_surfaces_have_dedicated_routes() -> None:
    navigation = read_source("services/web-ui/src/navigation.tsx")
    routes = read_source("services/web-ui/src/routes/routeRegistry.tsx")

    for view in ("agent-runs", "dependencies", "reports"):
        assert f'"{view}"' in navigation
        assert f'"{view}":' in routes or f"{view}:" in routes


def test_audit_runs_page_does_not_embed_result_tables() -> None:
    audit_runs_page = read_source("services/web-ui/src/pages/AuditRunsPage.tsx")

    assert "AgentRunsPage" not in audit_runs_page
    assert "ReportsPage" not in audit_runs_page
    assert "Tabs" not in audit_runs_page
    assert "List.Item.Meta" not in audit_runs_page
    assert "Descriptions.Item" not in audit_runs_page


def test_audit_runs_page_uses_focused_subcomponents() -> None:
    audit_runs_page = read_source("services/web-ui/src/pages/AuditRunsPage.tsx")

    for component in ("AuditRunActionBar", "AuditRunSummary", "RunContextPanel", "PipelineStatePanel"):
        assert component in audit_runs_page

    for path in (
        "services/web-ui/src/pages/audit-runs/AuditRunActionBar.tsx",
        "services/web-ui/src/pages/audit-runs/AuditRunSummary.tsx",
        "services/web-ui/src/pages/audit-runs/RunContextPanel.tsx",
        "services/web-ui/src/pages/audit-runs/PipelineStatePanel.tsx",
    ):
        assert (ROOT / path).is_file()


def test_projects_page_uses_focused_subcomponents() -> None:
    projects_page = read_source("services/web-ui/src/pages/ProjectsPage.tsx")

    assert "Descriptions.Item" not in projects_page
    assert "rowSelection" not in projects_page
    assert "Form.Item" not in projects_page
    for component in ("ProjectImportPanel", "SelectedProjectPanel", "ProjectInventoryTable"):
        assert component in projects_page

    for path in (
        "services/web-ui/src/pages/projects/ProjectImportPanel.tsx",
        "services/web-ui/src/pages/projects/SelectedProjectPanel.tsx",
        "services/web-ui/src/pages/projects/ProjectInventoryTable.tsx",
    ):
        assert (ROOT / path).is_file()


def test_runtime_page_uses_focused_subcomponents() -> None:
    runtime_page = read_source("services/web-ui/src/pages/RuntimePage.tsx")

    assert "List.Item.Meta" not in runtime_page
    assert "rowKey=\"Id\"" not in runtime_page
    for component in ("RuntimeActionBar", "RuntimeReadinessPanel", "RuntimeContainersPanel"):
        assert component in runtime_page

    for path in (
        "services/web-ui/src/pages/runtime/RuntimeActionBar.tsx",
        "services/web-ui/src/pages/runtime/RuntimeReadinessPanel.tsx",
        "services/web-ui/src/pages/runtime/RuntimeContainersPanel.tsx",
    ):
        assert (ROOT / path).is_file()


def test_admin_page_uses_focused_subcomponents() -> None:
    admin_page = read_source("services/web-ui/src/pages/AdminPage.tsx")

    assert "Form.Item" not in admin_page
    assert "runtimePolicy?.platform_audit_events" not in admin_page
    for component in ("PlatformAuditPanel", "ApiKeysPanel"):
        assert component in admin_page

    for path in (
        "services/web-ui/src/pages/admin/PlatformAuditPanel.tsx",
        "services/web-ui/src/pages/admin/ApiKeysPanel.tsx",
    ):
        assert (ROOT / path).is_file()


def test_findings_page_does_not_embed_dependency_inventory() -> None:
    findings_page = read_source("services/web-ui/src/pages/FindingsPage.tsx")

    assert "DependencyInventory" not in findings_page
    assert "DependenciesPage" not in findings_page
    assert "Tabs" not in findings_page


def test_app_shell_delegates_dashboard_state_to_controller_hook() -> None:
    app = read_source("services/web-ui/src/App.tsx")
    controller = read_source("services/web-ui/src/hooks/useDashboardController.tsx")

    assert "useDashboardController" in app
    assert "readJson(" not in app
    assert app.count("useState") == 0
    assert "<AppRoutes activeView={activeView} dashboard={dashboard} />" in app
    assert "useDashboardRefresh" in controller
    assert "useAuditRunActions" in controller
    assert "dashboardApi." not in controller
    assert "function runPipeline()" not in controller


def test_dashboard_controller_uses_domain_action_hooks() -> None:
    controller = read_source("services/web-ui/src/hooks/useDashboardController.tsx")

    for hook in (
        "useAdminActions",
        "useAuditRunActions",
        "useKnowledgeActions",
        "useProjectActions",
        "useRuntimeActions",
    ):
        assert hook in controller

    for path in (
        "services/web-ui/src/hooks/dashboard/useAdminActions.ts",
        "services/web-ui/src/hooks/dashboard/useAuditRunActions.ts",
        "services/web-ui/src/hooks/dashboard/useDashboardRefresh.ts",
        "services/web-ui/src/hooks/dashboard/useKnowledgeActions.ts",
        "services/web-ui/src/hooks/dashboard/useProjectActions.ts",
        "services/web-ui/src/hooks/dashboard/useRuntimeActions.ts",
    ):
        assert (ROOT / path).is_file()


def test_routes_use_dashboard_controller_instead_of_flat_prop_surface() -> None:
    routes = read_source("services/web-ui/src/routes/AppRoutes.tsx")

    assert "DashboardController" in routes
    assert "dashboard: DashboardController" in routes
    assert "onCreateGitProject:" not in routes
    assert "apiKeyForm: FormInstance" not in routes

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_audit_result_surfaces_have_dedicated_routes() -> None:
    navigation = read_source("services/web-ui/src/navigation.tsx")
    routes = read_source("services/web-ui/src/routes/routeRegistry.tsx")

    for view in (
        "agent-runs",
        "finding-review",
        "dependencies",
        "reports",
        "runtime-readiness",
        "runtime-containers",
        "runtime-sandbox",
    ):
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

    for component in ("AuditRunActionBar", "AuditRunConfigModal", "AuditRunSummary", "RunContextPanel", "PipelineStatePanel", "CodeAnalysisTasksPanel"):
        assert component in audit_runs_page

    for path in (
        "services/web-ui/src/pages/audit-runs/AuditRunActionBar.tsx",
        "services/web-ui/src/pages/audit-runs/AuditRunConfigModal.tsx",
        "services/web-ui/src/pages/audit-runs/AuditRunSummary.tsx",
        "services/web-ui/src/pages/audit-runs/CodeAnalysisTasksPanel.tsx",
        "services/web-ui/src/pages/audit-runs/RunContextPanel.tsx",
        "services/web-ui/src/pages/audit-runs/PipelineStatePanel.tsx",
    ):
        assert (ROOT / path).is_file()


def test_audit_run_config_modal_exposes_swarm_controls() -> None:
    modal = read_source("services/web-ui/src/pages/audit-runs/AuditRunConfigModal.tsx")
    api = read_source("services/web-ui/src/client/dashboardApi.ts")

    for field in (
        "enabled_agents",
        "preflight_prompt",
        "validator_rounds",
        "max_parallel_validators",
        "max_parallel_source_sink_finders",
        "max_parallel_judgers",
        "max_parallel_poc_writers",
        "max_parallel_poc_verifiers",
        "source_sink_finder_agent_name",
        "poc_verifier_agent_name",
        "enable_decompilation",
    ):
        assert field in modal

    assert "query_packs" not in modal

    assert "CreateAuditRunPayload" in api
    assert "createAuditRun(projectId: string, payload: CreateAuditRunPayload)" in api
    assert "Run an initial security audit" not in api


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
    runtime_readiness_page = read_source("services/web-ui/src/pages/RuntimeReadinessPage.tsx")
    runtime_containers_page = read_source("services/web-ui/src/pages/RuntimeContainersPage.tsx")
    runtime_sandbox_page = read_source("services/web-ui/src/pages/RuntimeSandboxPage.tsx")
    readiness_panel = read_source("services/web-ui/src/pages/runtime/RuntimeReadinessPanel.tsx")
    readiness_overview = read_source("services/web-ui/src/pages/runtime/ReadinessOverviewPanel.tsx")
    readiness_actions = read_source("services/web-ui/src/pages/runtime/ReadinessNextActionsPanel.tsx")
    containers_panel = read_source("services/web-ui/src/pages/runtime/RuntimeContainersPanel.tsx")
    sandbox_panel = read_source("services/web-ui/src/pages/runtime/RuntimeSandboxPanel.tsx")

    assert "List.Item.Meta" not in runtime_page
    assert "rowKey=\"Id\"" not in runtime_page
    assert "<Tabs" not in runtime_page
    assert 'onViewChange("runtime-readiness")' in runtime_page
    assert 'onViewChange("runtime-containers")' in runtime_page
    assert 'onViewChange("runtime-sandbox")' in runtime_page
    for component in ("RuntimeActionBar",):
        assert component in runtime_page

    assert "RuntimeReadinessPanel" in runtime_readiness_page
    assert "RuntimeContainersPanel" in runtime_containers_page
    assert "RuntimeSandboxPanel" in runtime_sandbox_page

    assert "List.Item.Meta" not in readiness_panel
    assert "rowKey=\"worker_id\"" not in readiness_panel
    for component in (
        "ReadinessCheckList",
        "ReadinessNextActionsPanel",
        "ReadinessOverviewPanel",
        "WorkerHeartbeatPanel",
    ):
        assert component in readiness_panel

    assert "Readiness data is unavailable" in readiness_panel
    assert "Readiness data is unavailable" in readiness_overview
    assert "Readiness data is unavailable" in readiness_actions
    assert 'name="command"' in sandbox_panel
    assert "onRunSandboxPoc" in sandbox_panel
    assert "onStartSandboxService" in sandbox_panel
    assert "Sandbox is using weak isolation" in sandbox_panel
    assert "Runtime containers are retained" in containers_panel


def test_pipeline_state_panel_surfaces_warning_events() -> None:
    panel = read_source("services/web-ui/src/pages/audit-runs/PipelineStatePanel.tsx")

    assert "completed_with_warnings" in panel
    assert "warningEvents" in panel

    for path in (
        "services/web-ui/src/pages/runtime/RuntimeActionBar.tsx",
        "services/web-ui/src/pages/RuntimeReadinessPage.tsx",
        "services/web-ui/src/pages/RuntimeContainersPage.tsx",
        "services/web-ui/src/pages/RuntimeSandboxPage.tsx",
        "services/web-ui/src/pages/runtime/RuntimeReadinessPanel.tsx",
        "services/web-ui/src/pages/runtime/RuntimeContainersPanel.tsx",
        "services/web-ui/src/pages/runtime/RuntimeSandboxPanel.tsx",
        "services/web-ui/src/pages/runtime/ReadinessCheckList.tsx",
        "services/web-ui/src/pages/runtime/ReadinessNextActionsPanel.tsx",
        "services/web-ui/src/pages/runtime/ReadinessOverviewPanel.tsx",
        "services/web-ui/src/pages/runtime/WorkerHeartbeatPanel.tsx",
    ):
        assert (ROOT / path).is_file()


def test_knowledge_page_uses_focused_subcomponents() -> None:
    knowledge_page = read_source("services/web-ui/src/pages/KnowledgePage.tsx")

    assert "Form.Item" not in knowledge_page
    assert "List.Item.Meta" not in knowledge_page
    assert "<Upload" not in knowledge_page
    for component in ("KnowledgeStatusPanel", "KnowledgeUploadPanel", "KnowledgeDocumentsPanel", "KnowledgeSearchPanel"):
        assert component in knowledge_page

    for path in (
        "services/web-ui/src/pages/knowledge/KnowledgeStatusPanel.tsx",
        "services/web-ui/src/pages/knowledge/KnowledgeUploadPanel.tsx",
        "services/web-ui/src/pages/knowledge/KnowledgeDocumentsPanel.tsx",
        "services/web-ui/src/pages/knowledge/KnowledgeSearchPanel.tsx",
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
    assert "filters: severityFilters" in findings_page
    assert "filters: statusFilters" in findings_page
    assert "filters: sourceFilters" in findings_page


def test_reports_page_supports_preview_and_quality_summary() -> None:
    reports_page = read_source("services/web-ui/src/pages/ReportsPage.tsx")
    app_drawers = read_source("services/web-ui/src/components/AppDrawers.tsx")

    assert "onGenerateReport" in reports_page
    assert "onOpenArtifact" in reports_page
    assert "onPreviewArtifact" in reports_page
    assert "parse warnings" in reports_page
    assert "tool failures" in reports_page
    assert "ArtifactPreviewDrawer" in app_drawers


def test_finding_review_has_dedicated_page_not_global_drawer() -> None:
    app_drawers = read_source("services/web-ui/src/components/AppDrawers.tsx")
    review_page = read_source("services/web-ui/src/pages/FindingReviewPage.tsx")
    detail_panel = read_source("services/web-ui/src/pages/findings/FindingDetailPanel.tsx")
    renderers = read_source("services/web-ui/src/routes/routeRenderers.tsx")

    assert "FindingDrawer" not in app_drawers
    assert "FindingDetailPanel" in review_page
    assert "PoC Execution" in detail_panel
    assert "Tracking Markdown" in detail_panel
    assert "finding_markdown" in detail_panel
    assert "onPreviewArtifact" in review_page
    assert "onPreviewArtifact" in detail_panel
    assert "onRunFindingPoc" in detail_panel
    assert "renderFindingReviewRoute" in renderers
    assert 'onViewChange("findings")' in renderers


def test_app_shell_delegates_dashboard_state_to_controller_hook() -> None:
    app = read_source("services/web-ui/src/App.tsx")
    controller = read_source("services/web-ui/src/hooks/useDashboardController.tsx")

    assert "useDashboardController" in app
    assert "AuditContextBar" in app
    assert "readJson(" not in app
    assert app.count("useState") == 0
    assert "<AppRoutes activeView={activeView} dashboard={dashboard} onViewChange={setActiveView} />" in app
    assert "useDashboardRefresh" in controller
    assert "useAuditRunActions" in controller
    assert "dashboardApi." not in controller
    assert "function runPipeline()" not in controller


def test_audit_context_is_shared_shell_component() -> None:
    context_bar = read_source("services/web-ui/src/components/AuditContextBar.tsx")
    audit_runs_page = read_source("services/web-ui/src/pages/AuditRunsPage.tsx")
    findings_page = read_source("services/web-ui/src/pages/FindingsPage.tsx")

    assert "aria-label=\"Audit context\"" in context_bar
    assert "onViewChange(\"projects\")" in context_bar
    assert "onViewChange(\"audit-runs\")" in context_bar
    assert "onViewChange(\"findings\")" in context_bar
    assert "onViewChange(\"reports\")" in context_bar
    assert "AuditContextBar" not in audit_runs_page
    assert "AuditContextBar" not in findings_page


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


def test_dashboard_refresh_is_scoped_to_active_view() -> None:
    app = read_source("services/web-ui/src/App.tsx")
    controller = read_source("services/web-ui/src/hooks/useDashboardController.tsx")
    refresh = read_source("services/web-ui/src/hooks/dashboard/useDashboardRefresh.ts")
    api = read_source("services/web-ui/src/client/dashboardApi.ts")

    assert "useDashboardController(activeView)" in app
    assert "useDashboardController(activeView: AppView)" in controller
    assert "refreshCurrentView(activeView)" in controller
    assert "async function refreshCurrentView(view: AppView)" in refresh
    for branch in (
        'case "projects"',
        'case "runtime"',
        'case "runtime-readiness"',
        'case "runtime-containers"',
        'case "runtime-sandbox"',
        'case "knowledge"',
        'case "admin"',
    ):
        assert branch in refresh
    assert "getDashboardProjects" not in api
    assert "getDashboardProjects" not in refresh


def test_web_ui_build_runs_typecheck() -> None:
    package_json = json.loads(read_source("services/web-ui/package.json"))

    assert "typecheck" in package_json["scripts"]
    assert "npm run typecheck" in package_json["scripts"]["build"]


def test_dashboard_api_client_uses_typed_json_boundaries() -> None:
    api = read_source("services/web-ui/src/client/dashboardApi.ts")
    state = read_source("services/web-ui/src/hooks/useDashboardState.tsx")
    overview = read_source("services/web-ui/src/pages/OverviewPage.tsx")
    drawers = read_source("services/web-ui/src/components/AppDrawers.tsx")

    for typed_call in (
        "readJson<ApiHealth>",
        "readJson<Project[]>",
        "readJson<AuditRun>",
        "readJson<AgentRun[]>",
        "readJson<ExecutionGraph>",
        "readJson<Finding[]>",
        "readJson<ContainerRow[]>",
        "readJson<PipelineStatus>",
        "postJson<CreateAuditRunResponse>",
        "postJson<KnowledgeSearchResponse>",
    ):
        assert typed_call in api

    assert "as Project[]" not in read_source("services/web-ui/src/hooks/dashboard/useDashboardRefresh.ts")
    assert "useState<ApiHealth>" in state
    assert "useState<DockerHealth>" in state
    assert "useState<AgentRunEvent[]>" in state
    assert "apiHealth?: any" not in overview
    assert "dockerHealth?: any" not in overview
    assert "agentEvents?: Array<Record<string, unknown>>" not in drawers


def test_routes_use_dashboard_controller_instead_of_flat_prop_surface() -> None:
    routes = read_source("services/web-ui/src/routes/AppRoutes.tsx")
    registry = read_source("services/web-ui/src/routes/routeRegistry.tsx")
    renderers = read_source("services/web-ui/src/routes/routeRenderers.tsx")

    assert "DashboardController" in routes
    assert "dashboard: DashboardController" in routes
    assert "onCreateGitProject:" not in routes
    assert "apiKeyForm: FormInstance" not in routes
    assert "routeRenderers" in registry
    assert "OverviewPage" not in registry
    assert "ProjectsPage" not in registry
    assert "RuntimePage" not in registry
    assert "renderProjectsRoute" in renderers
    assert "renderRuntimeRoute" in renderers


def test_app_drawers_delegate_to_focused_drawers() -> None:
    app_drawers = read_source("services/web-ui/src/components/AppDrawers.tsx")
    finding_detail = read_source("services/web-ui/src/pages/findings/FindingDetailPanel.tsx")

    assert "Descriptions.Item" not in app_drawers
    assert "List.Item.Meta" not in app_drawers
    assert "FindingDrawer" not in app_drawers
    assert "AgentEventsDrawer" in app_drawers
    assert "ContainerLogsDrawer" in app_drawers
    assert 'label: "PoC Execution"' in finding_detail
    assert 'name="command"' in finding_detail

    for path in (
        "services/web-ui/src/pages/findings/FindingDetailPanel.tsx",
        "services/web-ui/src/components/drawers/AgentEventsDrawer.tsx",
        "services/web-ui/src/components/drawers/ContainerLogsDrawer.tsx",
    ):
        assert (ROOT / path).is_file()

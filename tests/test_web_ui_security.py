from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_web_ui_does_not_request_weak_sandbox_isolation_by_default() -> None:
    app_source = (ROOT / "services/web-ui/src/hooks/dashboard/useRuntimeActions.ts").read_text(encoding="utf-8")

    assert "allow_weak_isolation: true" not in app_source
    assert "allow_weak_isolation: false" in app_source


def test_web_ui_does_not_enable_external_network_by_default() -> None:
    app_source = (ROOT / "services/web-ui/src/hooks/dashboard/useRuntimeActions.ts").read_text(encoding="utf-8")

    assert "allow_external_network: true" not in app_source
    assert "allow_external_network: false" in app_source


def test_web_ui_api_key_form_supports_artifact_scope_metadata() -> None:
    api_keys_panel = (ROOT / "services/web-ui/src/pages/admin/ApiKeysPanel.tsx").read_text(encoding="utf-8")
    admin_actions = (ROOT / "services/web-ui/src/hooks/dashboard/useAdminActions.ts").read_text(encoding="utf-8")
    columns = (ROOT / "services/web-ui/src/hooks/useDashboardColumns.tsx").read_text(encoding="utf-8")

    assert 'name="project_ids"' in api_keys_panel
    assert 'name="audit_run_ids"' in api_keys_panel
    assert "parseCsvList(values.project_ids)" in admin_actions
    assert "parseScopes(values.project_ids)" not in admin_actions
    assert "project_ids: projectIds" in admin_actions
    assert "audit_run_ids: auditRunIds" in admin_actions
    assert "project:" in columns
    assert "run:" in columns

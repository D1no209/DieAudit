from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, settings
from app.api import routes
import app.main as main_module


class _RejectingRuntime:
    async def run_poc_container(self, **kwargs):
        self.last_poc_kwargs = kwargs
        raise RuntimeError("sandbox network belongs to a different audit run: dieaudit-run-other-sandbox")


class _RecordingRuntime:
    async def start_agent_run(self, **kwargs):
        self.last_agent_kwargs = kwargs
        return {"ok": True, "agent_run_id": "agent-1", **kwargs}


async def _audit_run(audit_run_id: str):
    return {
        "audit_run_id": audit_run_id,
        "project_id": "project-1",
        "snapshot_id": None,
        "status": "created",
        "validator_rounds": 1,
        "max_parallel_validators": 2,
        "allow_external_network": False,
        "retain_runtime_on_failure": False,
        "config": {"workspace_host_path": "E:/Dino/DieAudit/data/workspaces/project-1"},
    }


async def _record_event(*_args, **_kwargs):
    return None


def _auth_headers() -> dict[str, str]:
    if not settings.dieaudit_api_key:
        return {}
    return {settings.api_key_header: settings.dieaudit_api_key}


def _restricted_headers() -> dict[str, str]:
    return {settings.api_key_header: "restricted-key"}


def _principal(project_ids=None, audit_run_ids=None):
    metadata = {}
    if project_ids is not None:
        metadata["project_ids"] = project_ids
    if audit_run_ids is not None:
        metadata["audit_run_ids"] = audit_run_ids
    return {"key_id": "restricted", "name": "restricted", "source": "test", "scopes": ["audit"], "metadata": metadata}


async def _auth_enabled(_settings):
    return True


def _authenticate_as(principal):
    async def _authenticate(_settings, _supplied):
        return principal

    return _authenticate


def test_audit_run_route_enforces_api_key_resource_scope(monkeypatch) -> None:
    async def audit_run_by_id(audit_run_id: str):
        if audit_run_id == "run-1":
            return {**await _audit_run(audit_run_id), "project_id": "project-1"}
        if audit_run_id == "run-2":
            return {**await _audit_run(audit_run_id), "project_id": "project-2"}
        return None

    monkeypatch.setattr(main_module, "auth_is_enabled", _auth_enabled)
    monkeypatch.setattr(main_module, "authenticate_api_key", _authenticate_as(_principal(project_ids=["project-1"])))
    monkeypatch.setattr(routes, "_get_audit_run", audit_run_by_id)

    client = TestClient(app)
    allowed = client.get("/audit-runs/run-1", headers=_restricted_headers())
    denied = client.get("/audit-runs/run-2", headers=_restricted_headers())

    assert allowed.status_code == 200
    assert allowed.json()["project_id"] == "project-1"
    assert denied.status_code == 403


def test_agent_run_route_rejects_project_mismatch_for_existing_audit_run(monkeypatch) -> None:
    runtime = _RecordingRuntime()
    monkeypatch.setattr(main_module, "runtime", runtime)
    monkeypatch.setattr(main_module, "auth_is_enabled", _auth_enabled)
    monkeypatch.setattr(main_module, "authenticate_api_key", _authenticate_as(_principal(audit_run_ids=["run-1"])))
    monkeypatch.setattr(routes, "_get_audit_run", _audit_run)

    client = TestClient(app)
    response = client.post(
        "/audit-runs/run-1/agent-runs",
        headers=_restricted_headers(),
        json={
            "audit_run_id": "run-1",
            "project_id": "project-2",
            "agent_name": "opencode-orchestrator",
        },
    )

    assert response.status_code == 400
    assert "project_id does not match audit run" in response.json()["detail"]
    assert not hasattr(runtime, "last_agent_kwargs")


def test_poc_api_rejects_external_network_when_platform_policy_disables_it(monkeypatch) -> None:
    runtime = _RejectingRuntime()
    monkeypatch.setattr(main_module, "runtime", runtime)
    monkeypatch.setattr(routes, "_get_audit_run", _audit_run)
    monkeypatch.setattr(routes, "_record_audit_run_event", _record_event)
    monkeypatch.setattr(settings, "allow_sandbox_external_network", False)

    client = TestClient(app)
    response = client.post(
        "/audit-runs/run-1/sandbox/poc",
        headers=_auth_headers(),
        json={
            "image": "python:3.12-slim",
            "command": ["python", "-c", "print('ok')"],
            "network_name": "dieaudit-run-other-sandbox",
            "allow_external_network": True,
            "allow_weak_isolation": True,
        },
    )

    assert response.status_code == 403
    assert "sandbox external network is disabled" in response.json()["detail"]
    assert not hasattr(runtime, "last_poc_kwargs")


def test_poc_api_rejects_runtime_network_policy_violation(monkeypatch) -> None:
    runtime = _RejectingRuntime()
    monkeypatch.setattr(main_module, "runtime", runtime)
    monkeypatch.setattr(routes, "_get_audit_run", _audit_run)
    monkeypatch.setattr(routes, "_record_audit_run_event", _record_event)
    monkeypatch.setattr(settings, "allow_sandbox_external_network", True)

    client = TestClient(app)
    response = client.post(
        "/audit-runs/run-1/sandbox/poc",
        headers=_auth_headers(),
        json={
            "image": "python:3.12-slim",
            "command": ["python", "-c", "print('ok')"],
            "network_name": "dieaudit-run-other-sandbox",
            "allow_external_network": True,
            "allow_weak_isolation": True,
        },
    )

    assert response.status_code == 400
    assert "different audit run" in response.json()["detail"]
    assert runtime.last_poc_kwargs["audit_run_id"] == "run-1"
    assert runtime.last_poc_kwargs["project_id"] == "project-1"
    assert runtime.last_poc_kwargs["network_name"] == "dieaudit-run-other-sandbox"
    assert runtime.last_poc_kwargs["allow_external_network"] is True


def test_opencode_demo_is_disabled_by_default(monkeypatch, tmp_path) -> None:
    runtime = _RecordingRuntime()
    monkeypatch.setattr(main_module, "runtime", runtime)
    monkeypatch.setattr(settings, "enable_demo_templates", False)
    monkeypatch.setattr(settings, "workspace_root", tmp_path)

    client = TestClient(app)
    response = client.post("/audit-runs/demo/opencode-demo", headers=_auth_headers())

    assert response.status_code == 403
    assert "demo templates are disabled" in response.json()["detail"]
    assert not hasattr(runtime, "last_agent_kwargs")


def test_opencode_demo_keeps_runtime_network_internal_when_enabled(monkeypatch, tmp_path) -> None:
    runtime = _RecordingRuntime()
    monkeypatch.setattr(main_module, "runtime", runtime)
    monkeypatch.setattr(settings, "enable_demo_templates", True)
    monkeypatch.setattr(settings, "workspace_root", tmp_path)

    client = TestClient(app)
    response = client.post("/audit-runs/demo/opencode-demo", headers=_auth_headers())

    assert response.status_code == 200
    assert runtime.last_agent_kwargs["project_id"] == "opencode-demo-project"
    assert runtime.last_agent_kwargs["agent_name"] == "opencode-orchestrator"
    assert runtime.last_agent_kwargs["allow_external_network"] is False

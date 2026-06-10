from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, settings
from app.api import routes
import app.main as main_module


class _RejectingRuntime:
    async def run_poc_container(self, **kwargs):
        self.last_poc_kwargs = kwargs
        raise RuntimeError("sandbox network belongs to a different audit run: dieaudit-run-other-sandbox")


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


def test_poc_api_rejects_runtime_network_policy_violation(monkeypatch) -> None:
    runtime = _RejectingRuntime()
    monkeypatch.setattr(main_module, "runtime", runtime)
    monkeypatch.setattr(routes, "_get_audit_run", _audit_run)
    monkeypatch.setattr(routes, "_record_audit_run_event", _record_event)

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

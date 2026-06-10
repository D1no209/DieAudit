from __future__ import annotations

from types import SimpleNamespace

from app.api.routes import _pipeline_backend_readiness_check


def test_pipeline_readiness_fails_background_tasks_backend() -> None:
    settings = SimpleNamespace(pipeline_execution_backend="background-tasks", pipeline_recovery_on_startup=True)

    check = _pipeline_backend_readiness_check(settings)

    assert check["status"] == "fail"
    assert check["detail"]["backend"] == "background-tasks"


def test_pipeline_readiness_passes_workflow_worker_backend() -> None:
    settings = SimpleNamespace(pipeline_execution_backend="workflow-worker", pipeline_recovery_on_startup=True)

    check = _pipeline_backend_readiness_check(settings, worker_health={"ok": True, "active_count": 1})

    assert check["status"] == "pass"
    assert check["detail"]["backend"] == "workflow-worker"


def test_pipeline_readiness_fails_workflow_worker_without_heartbeat() -> None:
    settings = SimpleNamespace(pipeline_execution_backend="workflow-worker", pipeline_recovery_on_startup=True)

    check = _pipeline_backend_readiness_check(settings, worker_health={"ok": False, "message": "No fresh worker"})

    assert check["status"] == "fail"
    assert check["detail"]["worker_health"]["ok"] is False


def test_pipeline_readiness_fails_unsupported_backend() -> None:
    settings = SimpleNamespace(pipeline_execution_backend="temporal", pipeline_recovery_on_startup=True)

    check = _pipeline_backend_readiness_check(settings)

    assert check["status"] == "fail"
    assert check["detail"]["backend"] == "temporal"

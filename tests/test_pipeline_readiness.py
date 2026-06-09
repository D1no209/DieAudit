from __future__ import annotations

from types import SimpleNamespace

from app.api.routes import _pipeline_backend_readiness_check


def test_pipeline_readiness_fails_background_tasks_backend() -> None:
    settings = SimpleNamespace(pipeline_execution_backend="background-tasks", pipeline_recovery_on_startup=True)

    check = _pipeline_backend_readiness_check(settings)

    assert check["status"] == "fail"
    assert check["detail"]["backend"] == "background-tasks"


def test_pipeline_readiness_passes_durable_backend() -> None:
    settings = SimpleNamespace(pipeline_execution_backend="temporal", pipeline_recovery_on_startup=True)

    check = _pipeline_backend_readiness_check(settings)

    assert check["status"] == "pass"

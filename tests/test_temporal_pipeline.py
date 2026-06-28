from pathlib import Path

from app.services.pipeline_executor import PipelineExecutor


ROOT = Path(__file__).resolve().parents[1]


def test_temporal_pipeline_service_was_removed() -> None:
    assert not (ROOT / "services/platform/app/services/temporal_pipeline.py").exists()


def test_temporal_sdk_dependency_was_removed() -> None:
    requirements = (ROOT / "services/platform/requirements.txt").read_text(encoding="utf-8")

    assert "temporalio" not in requirements


def test_pipeline_executor_does_not_expose_temporal_methods() -> None:
    names = set(dir(PipelineExecutor))

    assert not any(name.startswith(("prepare_temporal", "execute_temporal", "complete_temporal", "finalize_temporal", "fail_temporal")) for name in names)

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_routes_do_not_expose_temporal_health() -> None:
    source = (ROOT / "services/platform/app/api/routes.py").read_text(encoding="utf-8")

    assert "/runtime/temporal/health" not in source
    assert "_temporal_health" not in source
    assert "local hash embeddings are available but not semantic" in source
    assert "dieaudit_artifact_storage_backend" in source

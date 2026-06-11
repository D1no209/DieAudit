from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_e2e_status_endpoint_is_exposed() -> None:
    routes = read_source("services/platform/app/api/routes.py")

    assert '@router.get("/runtime/e2e/status")' in routes
    assert "model_configured" in routes
    assert "workflow_worker" in routes


def test_e2e_smoke_scripts_use_gateway_and_skip_pipeline_without_model_key() -> None:
    ps1 = read_source("scripts/e2e-smoke.ps1")
    sh = read_source("scripts/e2e-smoke.sh")

    for source in (ps1, sh):
        assert "http://localhost:8080/gateway" in source
        assert "/runtime/e2e/status" in source
        assert "/projects/upload-zip" in source
        assert "/run-pipeline" in source
        assert "model_configured" in source
        assert "control-plane" in source
        assert "http://127.0.0.1:7897" in source

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_backend_readiness_logic_is_not_embedded_in_routes() -> None:
    routes = read_source("services/platform/app/api/routes.py")
    readiness = read_source("services/platform/app/api/readiness.py")

    assert "from app.api.readiness import" in routes
    assert "def _template_readiness_checks(" not in routes
    assert "def _pipeline_backend_readiness_check(" not in routes
    assert "def template_readiness_checks(" in readiness
    assert "def pipeline_backend_readiness_check(" in readiness


def test_backend_serializers_are_not_embedded_in_routes() -> None:
    routes = read_source("services/platform/app/api/routes.py")
    serializers = read_source("services/platform/app/api/serializers.py")

    assert "from app.api.serializers import" in routes
    for local_function in (
        "def _agent_run_to_dict(",
        "def _project_to_dict(",
        "def _audit_run_to_dict(",
        "def _finding_to_dict(",
        "def _dependency_record_to_dict(",
    ):
        assert local_function not in routes

    for serializer_function in (
        "def agent_run_to_dict(",
        "def project_to_dict(",
        "def audit_run_to_dict(",
        "def finding_to_dict(",
        "def dependency_record_to_dict(",
    ):
        assert serializer_function in serializers

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_core_services_use_independent_images_and_dockerfiles() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    expected = {
        "web-api": ("dieaudit/web-api:local", "services/web-api/Dockerfile"),
        "workflow-worker": ("dieaudit/workflow-worker:local", "services/workflow-worker/Dockerfile"),
        "agent-gateway": ("dieaudit/agent-gateway:local", "services/agent-gateway/Dockerfile"),
        "workspace-engine": ("dieaudit/workspace-engine:local", "services/workspace-engine/Dockerfile"),
        "sandbox-runner": ("dieaudit/sandbox-runner:local", "services/sandbox-runner/Dockerfile"),
        "kb-indexer": ("dieaudit/kb-indexer:local", "services/kb-indexer/Dockerfile"),
    }

    for service_name, (image, dockerfile) in expected.items():
        service = services[service_name]
        assert service["image"] == image
        assert service["build"]["dockerfile"] == dockerfile


def test_worker_no_longer_depends_on_web_api_routes() -> None:
    worker_sources = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "services/workflow-worker/app").rglob("*.py"))

    assert "app.api.routes" not in worker_sources
    assert "StageRegistry" in worker_sources
    assert "PipelineStage" in worker_sources


def test_bff_and_internal_api_prefixes_are_present() -> None:
    web_api = read("services/web-api/app/main.py")
    worker = read("services/workflow-worker/app/main.py")
    agent_gateway = read("services/agent-gateway/app/main.py")

    assert "/api/bff" in web_api
    assert "/internal/pipelines" in worker
    assert "/internal/agent-runs" in agent_gateway


def test_alembic_baseline_is_present() -> None:
    assert (ROOT / "services/database/alembic/env.py").is_file()
    baseline = read("services/database/alembic/versions/0001_baseline.py")

    for table_name in ("pipeline_runs", "pipeline_stage_runs", "audit_events", "runtime_containers"):
        assert f'"{table_name}"' in baseline


def test_frontend_bff_domain_structure_exists() -> None:
    for path in (
        "services/web-ui/src/api/bffClient.ts",
        "services/web-ui/src/api/auditRuns.ts",
        "services/web-ui/src/domains/projects/useProjectsDomain.ts",
        "services/web-ui/src/domains/audit-runs/useAuditRunsDomain.ts",
        "services/web-ui/src/app/routes.tsx",
        "services/web-ui/src/shared/types/index.ts",
    ):
        assert (ROOT / path).is_file()

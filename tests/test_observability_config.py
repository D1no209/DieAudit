from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_grafana_observability_profile_provisions_prometheus_dashboard() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    grafana = compose["services"]["grafana"]
    volumes = "\n".join(grafana["volumes"])

    assert "./configs/observability/grafana/datasources:/etc/grafana/provisioning/datasources:ro" in volumes
    assert "./configs/observability/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro" in volumes
    assert "./configs/observability/grafana/dashboard-definitions:/var/lib/grafana/dashboards:ro" in volumes

    datasource = yaml.safe_load((ROOT / "configs/observability/grafana/datasources/prometheus.yml").read_text(encoding="utf-8"))
    assert datasource["datasources"][0]["url"] == "http://prometheus:9090"


def test_runtime_metrics_include_security_and_storage_signals() -> None:
    routes = (ROOT / "services/platform/app/api/routes.py").read_text(encoding="utf-8")

    assert "dieaudit_artifact_storage_backend" in routes
    assert "dieaudit_demo_templates_enabled" in routes
    assert "dieaudit_weak_runc_sandbox_enabled" in routes

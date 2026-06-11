from types import SimpleNamespace

import pytest

from app.api import routes


class _FakeWriter:
    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


class _FakeReader:
    def feed_eof(self) -> None:
        return None


@pytest.mark.asyncio
async def test_temporal_health_checks_configured_tcp_address(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_open_connection(host: str, port: int):
        captured["host"] = host
        captured["port"] = port
        return _FakeReader(), _FakeWriter()

    monkeypatch.setattr(routes.asyncio, "open_connection", fake_open_connection)

    result = await routes._temporal_health(SimpleNamespace(temporal_address="temporal:7233"))

    assert result["ok"] is True
    assert captured == {"host": "temporal", "port": 7233}


@pytest.mark.asyncio
async def test_temporal_health_rejects_invalid_port() -> None:
    result = await routes._temporal_health(SimpleNamespace(temporal_address="temporal:not-a-port"))

    assert result["ok"] is False
    assert "host:port" in result["error"]


def test_runtime_routes_expose_temporal_health_and_production_embedding_failure() -> None:
    source = (routes.Path(__file__).resolve().parents[1] / "services/platform/app/api/routes.py").read_text(encoding="utf-8")

    assert '@router.get("/runtime/temporal/health")' in source
    assert "local hash embeddings are development-only" in source
    assert "dieaudit_artifact_storage_backend" in source

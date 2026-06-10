from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import routes
from app.services.artifacts import (
    ArtifactAccessError,
    artifact_metadata,
    artifact_path_matches,
    resolve_artifact_path,
    secure_artifact_headers,
)


def test_resolve_artifact_path_accepts_relative_path_under_artifact_root(tmp_path: Path) -> None:
    artifact = tmp_path / "reports" / "run-1" / "report.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# report", encoding="utf-8")
    settings = SimpleNamespace(artifact_root=tmp_path)

    assert resolve_artifact_path(settings, "reports/run-1/report.md") == artifact.resolve()


def test_artifact_metadata_returns_download_url_for_safe_file(tmp_path: Path) -> None:
    artifact = tmp_path / "container-logs" / "run-1" / "agent.log"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("log", encoding="utf-8")
    settings = SimpleNamespace(artifact_root=tmp_path)

    metadata = artifact_metadata(settings, artifact)

    assert metadata["relative_path"] == "container-logs/run-1/agent.log"
    assert metadata["name"] == "agent.log"
    assert metadata["size"] == 3
    assert metadata["download_url"] == "/artifacts/download?path=container-logs/run-1/agent.log"


def test_resolve_artifact_path_rejects_path_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    settings = SimpleNamespace(artifact_root=tmp_path)

    with pytest.raises(ArtifactAccessError):
        resolve_artifact_path(settings, outside)


def test_artifact_path_matches_normalizes_stored_paths(tmp_path: Path) -> None:
    artifact = tmp_path / "reports" / "run-1" / "report.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# report", encoding="utf-8")
    settings = SimpleNamespace(artifact_root=tmp_path)

    assert artifact_path_matches(settings, "reports/run-1/report.md", artifact.resolve())
    assert artifact_path_matches(settings, artifact, artifact.resolve())


def test_artifact_path_matches_rejects_missing_or_escaping_stored_path(tmp_path: Path) -> None:
    artifact = tmp_path / "reports" / "run-1" / "report.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# report", encoding="utf-8")
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    settings = SimpleNamespace(artifact_root=tmp_path)

    assert not artifact_path_matches(settings, "missing.txt", artifact.resolve())
    assert not artifact_path_matches(settings, outside, artifact.resolve())


def test_secure_artifact_headers_disable_browser_execution_and_cache() -> None:
    headers = secure_artifact_headers()

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Security-Policy"] == "sandbox"
    assert "no-store" in headers["Cache-Control"]


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return iter(self.rows)


class _FakeSession:
    def __init__(self, calls):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, _query):
        rows = self.calls.pop(0) if self.calls else []
        return _FakeResult(rows)


def test_artifact_reference_check_allows_explicit_orm_reference(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    artifact = tmp_path / "reports" / "run-1" / "report.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# report", encoding="utf-8")
    settings = SimpleNamespace(artifact_root=tmp_path)

    monkeypatch.setattr(routes, "SessionLocal", lambda: _FakeSession([[str(artifact)]]))

    assert asyncio.run(routes._artifact_is_referenced(settings, artifact.resolve()))


def test_artifact_reference_check_denies_unreferenced_artifact(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    artifact = tmp_path / "reports" / "run-1" / "report.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# report", encoding="utf-8")
    settings = SimpleNamespace(artifact_root=tmp_path)

    monkeypatch.setattr(routes, "SessionLocal", lambda: _FakeSession([[], [], [], [], [], [], []]))

    assert not asyncio.run(routes._artifact_is_referenced(settings, artifact.resolve()))

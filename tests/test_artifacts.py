from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.artifacts import ArtifactAccessError, artifact_metadata, resolve_artifact_path, secure_artifact_headers


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


def test_secure_artifact_headers_disable_browser_execution_and_cache() -> None:
    headers = secure_artifact_headers()

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Security-Policy"] == "sandbox"
    assert "no-store" in headers["Cache-Control"]

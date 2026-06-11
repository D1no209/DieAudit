from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import routes
from app.services.artifacts import (
    ArtifactAccessError,
    ArtifactStore,
    artifact_id_for_relative_path,
    artifact_metadata,
    artifact_path_matches,
    relative_path_for_artifact_id,
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
    assert metadata["artifact_id"] == artifact_id_for_relative_path("container-logs/run-1/agent.log")
    assert metadata["artifact_uri"] == "local://artifacts/container-logs/run-1/agent.log"
    assert metadata["storage_backend"] == "local"
    assert metadata["content_type"] == "application/octet-stream"
    assert metadata["sha256"] == "836ff184e7b41b1e13cb5fd89fa1de98dbbab99e9d2918913ff43b86a5c7c213"
    assert metadata["name"] == "agent.log"
    assert metadata["size"] == 3
    assert metadata["download_url"] == "/artifacts/download?path=container-logs/run-1/agent.log"
    assert metadata["canonical_download_url"].startswith("/artifacts/")


def test_artifact_store_put_text_returns_canonical_metadata(tmp_path: Path) -> None:
    settings = SimpleNamespace(artifact_root=tmp_path, artifact_storage_backend="local")

    metadata = ArtifactStore(settings).put_text("reports/run-1/report.md", "# report", content_type="text/markdown")

    assert (tmp_path / "reports" / "run-1" / "report.md").read_text(encoding="utf-8") == "# report"
    assert metadata["artifact_uri"] == "local://artifacts/reports/run-1/report.md"
    assert metadata["content_type"] == "text/markdown"
    assert metadata["sha256"] == "f1e08744499eea1390fb33c5cebf61eb9a43aeab92bb864d6c65545062267d00"


def test_artifact_store_minio_reads_object_without_local_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    objects: dict[tuple[str, str], dict[str, object]] = {}

    class _FakeStat:
        def __init__(self, data: bytes, content_type: str, metadata: dict[str, str]):
            self.size = len(data)
            self.content_type = content_type
            self.metadata = metadata
            self.last_modified = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class _FakeResponse:
        def __init__(self, data: bytes):
            self._data = data

        def read(self) -> bytes:
            return self._data

        def close(self) -> None:
            return None

        def release_conn(self) -> None:
            return None

    class _FakeMinio:
        def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool):
            self.endpoint = endpoint
            self.access_key = access_key
            self.secret_key = secret_key
            self.secure = secure

        def put_object(self, bucket: str, name: str, data, length: int, content_type: str, metadata: dict[str, str]):
            objects[(bucket, name)] = {
                "data": data.read(),
                "content_type": content_type,
                "metadata": {f"X-Amz-Meta-{key}": value for key, value in metadata.items()},
            }

        def stat_object(self, bucket: str, name: str):
            item = objects[(bucket, name)]
            return _FakeStat(item["data"], item["content_type"], item["metadata"])

        def get_object(self, bucket: str, name: str):
            return _FakeResponse(objects[(bucket, name)]["data"])

    monkeypatch.setitem(sys.modules, "minio", SimpleNamespace(Minio=_FakeMinio))
    settings = SimpleNamespace(
        artifact_root=tmp_path,
        artifact_storage_backend="minio",
        minio_endpoint="http://minio:9000",
        minio_access_key="dieaudit",
        minio_secret_key="secret",
        minio_bucket_artifacts="dieaudit-artifacts",
    )

    store = ArtifactStore(settings)
    written = store.put_text("reports/run-1/report.md", "# report", content_type="text/markdown")
    Path(written["path"]).unlink()

    metadata = store.metadata_for_path("reports/run-1/report.md")
    blob = store.get_blob("reports/run-1/report.md")

    assert metadata["artifact_uri"] == "minio://dieaudit-artifacts/reports/run-1/report.md"
    assert metadata["storage_backend"] == "minio"
    assert metadata["sha256"] == written["sha256"]
    assert blob.name == "report.md"
    assert blob.content_type == "text/markdown"
    assert blob.data == b"# report"


def test_artifact_id_round_trips_relative_path() -> None:
    artifact_id = artifact_id_for_relative_path("reports/run-1/report.md")

    assert relative_path_for_artifact_id(artifact_id) == "reports/run-1/report.md"


def test_artifact_id_rejects_invalid_or_absolute_paths() -> None:
    with pytest.raises(ArtifactAccessError, match="invalid artifact id"):
        relative_path_for_artifact_id("%%%")

    absolute_id = artifact_id_for_relative_path("/etc/passwd")
    with pytest.raises(ArtifactAccessError, match="invalid artifact id"):
        relative_path_for_artifact_id(absolute_id)


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


def _artifact_reference_calls(row):
    return [[], [], [], [], [], [], [row]]


def test_artifact_reference_check_allows_explicit_orm_reference(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    artifact = tmp_path / "reports" / "run-1" / "report.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# report", encoding="utf-8")
    settings = SimpleNamespace(artifact_root=tmp_path)
    report = SimpleNamespace(
        path=str(artifact),
        summary={},
        project_id="project-1",
        audit_run_id="run-1",
        report_id="report-1",
    )

    monkeypatch.setattr(routes, "SessionLocal", lambda: _FakeSession(_artifact_reference_calls(report)))

    assert asyncio.run(routes._artifact_is_referenced(settings, artifact.resolve()))


def test_artifact_reference_check_denies_unreferenced_artifact(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    artifact = tmp_path / "reports" / "run-1" / "report.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# report", encoding="utf-8")
    settings = SimpleNamespace(artifact_root=tmp_path)

    monkeypatch.setattr(routes, "SessionLocal", lambda: _FakeSession([[], [], [], [], [], [], []]))

    assert not asyncio.run(routes._artifact_is_referenced(settings, artifact.resolve()))


def test_artifact_reference_check_allows_finding_tracking_markdown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "findings" / "run-1" / "finding-1" / "finding.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Finding", encoding="utf-8")
    settings = SimpleNamespace(artifact_root=tmp_path)
    finding = SimpleNamespace(
        audit_run_id="run-1",
        finding_id="finding-1",
        project_id="project-1",
    )

    monkeypatch.setattr(routes, "SessionLocal", lambda: _FakeSession([[], [], [], [], [finding], [], []]))

    references = asyncio.run(routes._artifact_references(settings, artifact.resolve()))

    assert references == [
        {
            "kind": "finding_markdown",
            "project_id": "project-1",
            "audit_run_id": "run-1",
            "record_id": "finding-1",
        }
    ]


def test_principal_artifact_scope_allows_matching_project_or_audit_run() -> None:
    references = [
        {"kind": "report", "project_id": "project-1", "audit_run_id": "run-1", "record_id": "report-1"},
    ]

    assert routes._principal_can_access_artifact({"scopes": ["audit"], "metadata": {"project_ids": ["project-1"]}}, references)
    assert routes._principal_can_access_artifact({"scopes": ["read"], "metadata": {"audit_run_ids": "run-1"}}, references)


def test_principal_artifact_scope_denies_mismatched_project_or_audit_run() -> None:
    references = [
        {"kind": "report", "project_id": "project-1", "audit_run_id": "run-1", "record_id": "report-1"},
    ]

    assert not routes._principal_can_access_artifact({"scopes": ["audit"], "metadata": {"project_ids": ["project-2"]}}, references)
    assert not routes._principal_can_access_artifact(
        {"scopes": ["read"], "metadata": {"project_ids": ["project-1"], "audit_run_ids": ["run-2"]}},
        references,
    )


def test_principal_artifact_scope_remains_unrestricted_without_metadata_limits() -> None:
    references = [
        {"kind": "report", "project_id": "project-1", "audit_run_id": "run-1", "record_id": "report-1"},
    ]

    assert routes._principal_can_access_artifact({"scopes": ["read"], "metadata": {}}, references)
    assert routes._principal_can_access_artifact({"scopes": ["admin"], "metadata": {"project_ids": ["other"]}}, references)


def test_principal_resource_scope_allows_matching_audit_run() -> None:
    audit_run = {"audit_run_id": "run-1", "project_id": "project-1"}

    assert routes._principal_can_access_audit_run({"scopes": ["audit"], "metadata": {"project_ids": ["project-1"]}}, audit_run)
    assert routes._principal_can_access_audit_run({"scopes": ["audit"], "metadata": {"audit_run_ids": ["run-1"]}}, audit_run)
    assert routes._principal_can_access_audit_run(
        {"scopes": ["audit"], "metadata": {"project_ids": ["project-1"], "audit_run_ids": ["run-1"]}},
        audit_run,
    )


def test_principal_resource_scope_denies_mismatched_audit_run() -> None:
    audit_run = {"audit_run_id": "run-1", "project_id": "project-1"}

    assert not routes._principal_can_access_audit_run({"scopes": ["audit"], "metadata": {"project_ids": ["project-2"]}}, audit_run)
    assert not routes._principal_can_access_audit_run({"scopes": ["audit"], "metadata": {"audit_run_ids": ["run-2"]}}, audit_run)
    assert not routes._principal_can_access_audit_run(
        {"scopes": ["audit"], "metadata": {"project_ids": ["project-1"], "audit_run_ids": ["run-2"]}},
        audit_run,
    )


def test_principal_resource_scope_remains_unrestricted_without_metadata_limits() -> None:
    audit_run = {"audit_run_id": "run-1", "project_id": "project-1"}

    assert routes._principal_can_access_audit_run({"scopes": ["read"], "metadata": {}}, audit_run)
    assert routes._principal_can_access_audit_run({"scopes": ["admin"], "metadata": {"project_ids": ["project-2"]}}, audit_run)
    assert asyncio.run(routes._principal_can_access_project({"scopes": ["read"], "metadata": {}}, "project-1"))
    assert asyncio.run(routes._principal_can_access_project({"scopes": ["admin"], "metadata": {"project_ids": ["project-2"]}}, "project-1"))


def test_principal_project_scope_uses_direct_project_metadata() -> None:
    assert asyncio.run(routes._principal_can_access_project({"scopes": ["audit"], "metadata": {"project_ids": "project-1"}}, "project-1"))
    assert not asyncio.run(
        routes._principal_can_access_project({"scopes": ["audit"], "metadata": {"project_ids": ["project-2"]}}, "project-1")
    )


def test_resource_limit_detection_supports_legacy_metadata_aliases() -> None:
    assert routes._principal_has_resource_limits({"scopes": ["audit"], "metadata": {"projects": ["project-1"]}})
    assert routes._principal_has_resource_limits({"scopes": ["audit"], "metadata": {"audit_runs": "run-1"}})
    assert not routes._principal_has_resource_limits({"scopes": ["audit"], "metadata": {}})


def test_tool_result_metadata_keeps_execution_evidence_fields() -> None:
    metadata = routes._tool_result_metadata(
        {
            "ok": False,
            "tool": "semgrep",
            "command": ["semgrep", "--json", "."],
            "cwd": "/workspace/project",
            "exit_code": 2,
            "error": "scan failed",
            "timeout_seconds": 60,
            "stdout": "large output omitted",
            "secret": "must-not-leak",
        }
    )

    assert metadata == {
        "ok": False,
        "tool": "semgrep",
        "command": ["semgrep", "--json", "."],
        "cwd": "/workspace/project",
        "exit_code": 2,
        "error": "scan failed",
        "timeout_seconds": 60,
    }


def test_tool_evidence_payload_embeds_compact_execution_metadata() -> None:
    payload = routes._tool_evidence_payload(
        {"title": "SQL injection", "file_path": "app.py"},
        {"ok": True, "tool": "osv", "command": ["osv-scanner"], "ignored": {"nested": "value"}},
    )

    assert payload["title"] == "SQL injection"
    assert payload["tool_execution"]["tool"] == "osv"
    assert payload["tool_execution"]["command"] == ["osv-scanner"]
    assert "ignored" in payload["tool_execution"]


def test_platform_joern_artifact_path_maps_container_artifacts_to_run_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(artifact_root=tmp_path))

    path = routes._platform_joern_artifact_path("run-1", "/artifacts/joern-mcp/joern/cpg.bin.zip")

    assert path == tmp_path / "joern" / "run-1" / "joern-mcp" / "joern" / "cpg.bin.zip"

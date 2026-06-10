from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from app.services.workspace import WorkspaceImportError, WorkspaceService


def _settings(tmp_path: Path, **overrides):
    values = {
        "workspace_root": tmp_path / "workspaces",
        "artifact_root": tmp_path / "artifacts",
        "max_upload_bytes": 1024 * 1024,
        "max_workspace_files": 10,
        "max_workspace_uncompressed_bytes": 1024 * 1024,
        "allowed_git_url_schemes": "https,ssh",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _zip_bytes(entries: dict[str, bytes]) -> BytesIO:
    data = BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    data.seek(0)
    return data


def test_import_zip_rejects_too_many_files(tmp_path: Path) -> None:
    service = WorkspaceService(_settings(tmp_path, max_workspace_files=1))

    with pytest.raises(WorkspaceImportError, match="too many files"):
        service.import_zip(
            project_id="project",
            filename="project.zip",
            stream=_zip_bytes({"a.txt": b"a", "b.txt": b"b"}),
        )


def test_import_zip_rejects_uncompressed_size_limit(tmp_path: Path) -> None:
    service = WorkspaceService(_settings(tmp_path, max_workspace_uncompressed_bytes=3))

    with pytest.raises(WorkspaceImportError, match="uncompressed size"):
        service.import_zip(
            project_id="project",
            filename="project.zip",
            stream=_zip_bytes({"a.txt": b"abcd"}),
        )


def test_import_zip_rejects_symlink_entries(tmp_path: Path) -> None:
    data = BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "target")
    data.seek(0)
    service = WorkspaceService(_settings(tmp_path))

    with pytest.raises(WorkspaceImportError, match="symlink"):
        service.import_zip(project_id="project", filename="project.zip", stream=data)


def test_import_zip_rejects_upload_size_limit(tmp_path: Path) -> None:
    service = WorkspaceService(_settings(tmp_path, max_upload_bytes=4))

    with pytest.raises(WorkspaceImportError, match="upload exceeds"):
        service.import_zip(project_id="project", filename="project.zip", stream=BytesIO(b"12345"))

    assert list((tmp_path / "artifacts" / "uploads" / "project").glob("*")) == []


def test_git_url_validation_blocks_local_and_file_urls(tmp_path: Path) -> None:
    service = WorkspaceService(_settings(tmp_path))

    with pytest.raises(WorkspaceImportError, match="local Git paths"):
        service._validate_git_url("../repo")
    with pytest.raises(WorkspaceImportError, match="file://"):
        service._validate_git_url("file:///tmp/repo")


def test_git_url_validation_allows_https_and_scp_like_ssh(tmp_path: Path) -> None:
    service = WorkspaceService(_settings(tmp_path))

    service._validate_git_url("https://github.com/example/repo.git")
    service._validate_git_url("git@github.com:example/repo.git")

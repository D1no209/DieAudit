from __future__ import annotations

import hashlib
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO

from app.settings import Settings


class WorkspaceImportError(RuntimeError):
    pass


class WorkspaceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def import_git(self, *, project_id: str, git_url: str, ref: str | None = None) -> dict[str, str | None]:
        snapshot_id = self._snapshot_id()
        workspace_path = self._workspace_path(project_id, snapshot_id)
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone", "--depth", "1"]
        if ref:
            command.extend(["--branch", ref])
        command.extend([git_url, str(workspace_path)])
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise WorkspaceImportError((result.stderr or result.stdout or "git clone failed").strip())
        return self._snapshot_result(
            project_id=project_id,
            snapshot_id=snapshot_id,
            workspace_path=workspace_path,
            source_ref=ref or git_url,
            source_type="git",
        )

    def import_zip(self, *, project_id: str, filename: str, stream: BinaryIO) -> dict[str, str | None]:
        snapshot_id = self._snapshot_id()
        workspace_path = self._workspace_path(project_id, snapshot_id)
        archive_source = self.settings.artifact_root / "uploads" / project_id / f"{snapshot_id}-{Path(filename).name}"
        archive_source.parent.mkdir(parents=True, exist_ok=True)
        with archive_source.open("wb") as handle:
            shutil.copyfileobj(stream, handle)
        workspace_path.mkdir(parents=True, exist_ok=True)
        try:
            self._extract_zip(archive_source, workspace_path)
        except zipfile.BadZipFile as exc:
            raise WorkspaceImportError("invalid zip archive") from exc
        return self._snapshot_result(
            project_id=project_id,
            snapshot_id=snapshot_id,
            workspace_path=workspace_path,
            source_ref=filename,
            source_type="zip",
        )

    def _snapshot_result(
        self,
        *,
        project_id: str,
        snapshot_id: str,
        workspace_path: Path,
        source_ref: str | None,
        source_type: str,
    ) -> dict[str, str | None]:
        artifact_path = self._archive_snapshot(project_id, snapshot_id, workspace_path)
        return {
            "snapshot_id": snapshot_id,
            "project_id": project_id,
            "source_type": source_type,
            "source_ref": source_ref,
            "workspace_path": str(workspace_path),
            "artifact_path": str(artifact_path),
            "content_hash": self._sha256(artifact_path),
        }

    def _workspace_path(self, project_id: str, snapshot_id: str) -> Path:
        return self.settings.workspace_root / project_id / snapshot_id

    def _archive_snapshot(self, project_id: str, snapshot_id: str, workspace_path: Path) -> Path:
        archive_base = self.settings.artifact_root / "snapshots" / project_id / snapshot_id
        archive_base.parent.mkdir(parents=True, exist_ok=True)
        archive_file = shutil.make_archive(str(archive_base), "zip", root_dir=workspace_path)
        return Path(archive_file)

    @staticmethod
    def _snapshot_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _extract_zip(archive: Path, target: Path) -> None:
        target_root = target.resolve()
        with zipfile.ZipFile(archive) as zip_file:
            for item in zip_file.infolist():
                destination = (target / item.filename).resolve()
                if destination != target_root and target_root not in destination.parents:
                    raise WorkspaceImportError(f"zip entry escapes target directory: {item.filename}")
            zip_file.extractall(target)

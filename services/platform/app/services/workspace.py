from __future__ import annotations

import hashlib
import ipaddress
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path
from stat import S_IFMT, S_IFLNK
from typing import BinaryIO
from urllib.parse import urlparse

from app.settings import Settings


class WorkspaceImportError(RuntimeError):
    pass


class WorkspaceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def import_git(self, *, project_id: str, git_url: str, ref: str | None = None) -> dict[str, str | None]:
        self._validate_git_url(git_url)
        snapshot_id = self._snapshot_id()
        workspace_path = self._workspace_path(project_id, snapshot_id)
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone", "--depth", "1"]
        if ref:
            command.extend(["--branch", ref])
        command.extend(["--", git_url, str(workspace_path)])
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
        try:
            with archive_source.open("wb") as handle:
                self._copy_limited(stream, handle, max_bytes=self._max_upload_bytes())
        except WorkspaceImportError:
            archive_source.unlink(missing_ok=True)
            raise
        workspace_path.mkdir(parents=True, exist_ok=True)
        try:
            self._extract_zip(archive_source, workspace_path)
        except zipfile.BadZipFile as exc:
            shutil.rmtree(workspace_path, ignore_errors=True)
            raise WorkspaceImportError("invalid zip archive") from exc
        except RuntimeError as exc:
            shutil.rmtree(workspace_path, ignore_errors=True)
            raise WorkspaceImportError(f"failed to extract zip archive: {exc}") from exc
        except WorkspaceImportError:
            shutil.rmtree(workspace_path, ignore_errors=True)
            raise
        return {
            "snapshot_id": snapshot_id,
            "project_id": project_id,
            "source_type": "zip",
            "source_ref": filename,
            "workspace_path": str(workspace_path),
            "artifact_path": str(archive_source),
            "content_hash": self._sha256(archive_source),
        }

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

    def _extract_zip(self, archive: Path, target: Path) -> None:
        target_root = target.resolve()
        max_files = self._max_workspace_files()
        max_uncompressed = self._max_workspace_uncompressed_bytes()
        total_files = 0
        total_uncompressed = 0
        with zipfile.ZipFile(archive) as zip_file:
            for item in zip_file.infolist():
                if item.flag_bits & 0x1:
                    raise WorkspaceImportError(f"encrypted zip entries are not allowed: {item.filename}")
                if self._is_zip_symlink(item):
                    raise WorkspaceImportError(f"zip symlink entries are not allowed: {item.filename}")
                if item.is_dir():
                    continue
                total_files += 1
                total_uncompressed += item.file_size
                if max_files > 0 and total_files > max_files:
                    raise WorkspaceImportError(f"zip contains too many files: limit {max_files}")
                if max_uncompressed > 0 and total_uncompressed > max_uncompressed:
                    raise WorkspaceImportError(f"zip uncompressed size exceeds {max_uncompressed} bytes")
                destination = (target / item.filename).resolve()
                if destination != target_root and target_root not in destination.parents:
                    raise WorkspaceImportError(f"zip entry escapes target directory: {item.filename}")
            for item in zip_file.infolist():
                if item.is_dir():
                    continue
                destination = (target / item.filename).resolve()
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zip_file.open(item, "r") as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)

    def _copy_limited(self, source: BinaryIO, target: BinaryIO, *, max_bytes: int) -> int:
        copied = 0
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            copied += len(chunk)
            if max_bytes > 0 and copied > max_bytes:
                raise WorkspaceImportError(f"upload exceeds {max_bytes} bytes")
            target.write(chunk)
        return copied

    def _validate_git_url(self, git_url: str) -> None:
        value = (git_url or "").strip()
        if not value:
            raise WorkspaceImportError("git_url is required")
        allowed = self._allowed_git_url_schemes()
        if self._is_scp_like_git_url(value):
            if "ssh" not in allowed:
                raise WorkspaceImportError("scp-like Git SSH URLs are not allowed by ALLOWED_GIT_URL_SCHEMES")
            self._validate_git_host(self._scp_like_git_host(value))
            return
        parsed = urlparse(value)
        scheme = parsed.scheme.lower()
        if not scheme:
            raise WorkspaceImportError("local Git paths are not allowed; use an allowed remote URL scheme")
        if scheme == "file":
            raise WorkspaceImportError("file:// Git URLs are not allowed")
        if scheme not in allowed:
            raise WorkspaceImportError(f"Git URL scheme '{scheme}' is not allowed")
        if scheme in {"http", "https", "ssh", "git"} and not parsed.netloc:
            raise WorkspaceImportError("Git URL host is required")
        self._validate_git_host(parsed.hostname)

    def _allowed_git_url_schemes(self) -> set[str]:
        raw = str(getattr(self.settings, "allowed_git_url_schemes", "https,ssh") or "")
        return {item.strip().lower() for item in raw.split(",") if item.strip()}

    def _allowed_git_hosts(self) -> set[str]:
        raw = str(getattr(self.settings, "allowed_git_hosts", "") or "")
        return {self._normalize_host(item) for item in raw.split(",") if item.strip()}

    def _validate_git_host(self, host: str | None) -> None:
        normalized = self._normalize_host(host or "")
        if not normalized:
            raise WorkspaceImportError("Git URL host is required")
        if normalized in self._allowed_git_hosts():
            return
        if normalized == "localhost" or normalized.endswith(".localhost"):
            raise WorkspaceImportError("Git URL host is not allowed: localhost")
        try:
            ip = ipaddress.ip_address(normalized)
        except ValueError:
            return
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise WorkspaceImportError(f"Git URL host is not allowed: {normalized}")

    @staticmethod
    def _is_scp_like_git_url(value: str) -> bool:
        if "://" in value or value.startswith(("/", ".")):
            return False
        return "@" in value and ":" in value.split("@", 1)[1]

    @staticmethod
    def _scp_like_git_host(value: str) -> str:
        after_user = value.split("@", 1)[1] if "@" in value else value
        return after_user.split(":", 1)[0]

    @staticmethod
    def _normalize_host(host: str) -> str:
        return host.strip().strip("[]").rstrip(".").lower()

    @staticmethod
    def _is_zip_symlink(item: zipfile.ZipInfo) -> bool:
        mode = item.external_attr >> 16
        return S_IFMT(mode) == S_IFLNK

    def _max_upload_bytes(self) -> int:
        return int(getattr(self.settings, "max_upload_bytes", 104857600) or 0)

    def _max_workspace_files(self) -> int:
        return int(getattr(self.settings, "max_workspace_files", 20000) or 0)

    def _max_workspace_uncompressed_bytes(self) -> int:
        return int(getattr(self.settings, "max_workspace_uncompressed_bytes", 536870912) or 0)

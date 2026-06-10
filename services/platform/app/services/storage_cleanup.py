from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from app.settings import Settings


class StorageCleanupError(ValueError):
    pass


@dataclass(frozen=True)
class CleanupPolicy:
    runtime_package_retention_days: int
    upload_staging_retention_days: int
    unreferenced_workspace_retention_days: int
    unreferenced_snapshot_retention_days: int
    max_entries: int


class StorageCleanupService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def policy(
        self,
        *,
        runtime_package_retention_days: int | None = None,
        upload_staging_retention_days: int | None = None,
        unreferenced_workspace_retention_days: int | None = None,
        unreferenced_snapshot_retention_days: int | None = None,
        max_entries: int | None = None,
    ) -> CleanupPolicy:
        return CleanupPolicy(
            runtime_package_retention_days=self._non_negative(
                runtime_package_retention_days, self.settings.runtime_package_retention_days
            ),
            upload_staging_retention_days=self._non_negative(
                upload_staging_retention_days, self.settings.upload_staging_retention_days
            ),
            unreferenced_workspace_retention_days=self._non_negative(
                unreferenced_workspace_retention_days, self.settings.unreferenced_workspace_retention_days
            ),
            unreferenced_snapshot_retention_days=self._non_negative(
                unreferenced_snapshot_retention_days, self.settings.unreferenced_snapshot_retention_days
            ),
            max_entries=max(1, int(max_entries or self.settings.storage_cleanup_max_entries)),
        )

    def summary(self) -> dict[str, Any]:
        artifact_root = self.settings.artifact_root.resolve()
        workspace_root = self.settings.workspace_root.resolve()
        return {
            "roots": {
                "artifact_root": self._root_summary(artifact_root),
                "workspace_root": self._root_summary(workspace_root),
            },
            "managed_prefixes": {
                "runtime_packages": self._root_summary(artifact_root / "runtime-packages"),
                "upload_staging": self._root_summary(artifact_root / "uploads"),
                "snapshot_archives": self._root_summary(artifact_root / "snapshots"),
                "workspaces": self._root_summary(workspace_root),
            },
            "policy": self.policy().__dict__,
        }

    def cleanup(
        self,
        *,
        dry_run: bool,
        policy: CleanupPolicy,
        referenced_workspace_paths: Iterable[str | Path] = (),
        referenced_snapshot_paths: Iterable[str | Path] = (),
    ) -> dict[str, Any]:
        referenced_workspaces = self._resolved_existing(referenced_workspace_paths)
        referenced_snapshots = self._resolved_existing(referenced_snapshot_paths)
        now = datetime.now(timezone.utc)
        candidates: list[dict[str, Any]] = []
        candidates.extend(
            self._expired_children(
                root=self.settings.artifact_root / "runtime-packages",
                kind="runtime_package",
                retention_days=policy.runtime_package_retention_days,
                now=now,
                referenced_paths=[],
            )
        )
        candidates.extend(
            self._expired_children(
                root=self.settings.artifact_root / "uploads",
                kind="upload_staging",
                retention_days=policy.upload_staging_retention_days,
                now=now,
                referenced_paths=[],
            )
        )
        candidates.extend(
            self._expired_nested_children(
                root=self.settings.workspace_root,
                kind="unreferenced_workspace",
                retention_days=policy.unreferenced_workspace_retention_days,
                now=now,
                referenced_paths=referenced_workspaces,
            )
        )
        candidates.extend(
            self._expired_nested_children(
                root=self.settings.artifact_root / "snapshots",
                kind="unreferenced_snapshot_archive",
                retention_days=policy.unreferenced_snapshot_retention_days,
                now=now,
                referenced_paths=referenced_snapshots,
            )
        )
        candidates.sort(key=lambda item: (item["mtime"], item["path"]))
        truncated = len(candidates) > policy.max_entries
        selected = candidates[: policy.max_entries]
        deleted: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        if not dry_run:
            for item in selected:
                path = Path(item["path"])
                try:
                    self._delete_candidate(path)
                    deleted.append(item)
                except Exception as exc:
                    errors.append({**item, "error": str(exc)})
        return {
            "dry_run": dry_run,
            "policy": policy.__dict__,
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "truncated": truncated,
            "deleted_count": len(deleted),
            "error_count": len(errors),
            "candidates": selected,
            "deleted": deleted,
            "errors": errors,
        }

    def _expired_children(
        self,
        *,
        root: Path,
        kind: str,
        retention_days: int,
        now: datetime,
        referenced_paths: list[Path],
    ) -> list[dict[str, Any]]:
        root = root.resolve()
        self._assert_managed_root(root)
        if not root.exists():
            return []
        cutoff = now - timedelta(days=retention_days)
        rows: list[dict[str, Any]] = []
        for child in root.iterdir():
            resolved = child.resolve()
            self._assert_child(root, resolved)
            if self._contains_reference(resolved, referenced_paths):
                continue
            stat = resolved.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            if mtime > cutoff:
                continue
            rows.append(
                {
                    "kind": kind,
                    "path": str(resolved),
                    "relative_path": self._relative_storage_path(resolved),
                    "mtime": mtime.isoformat(),
                    "age_days": int((now - mtime).total_seconds() // 86400),
                    "bytes": self._path_size(resolved),
                }
            )
        return rows

    def _expired_nested_children(
        self,
        *,
        root: Path,
        kind: str,
        retention_days: int,
        now: datetime,
        referenced_paths: list[Path],
    ) -> list[dict[str, Any]]:
        root = root.resolve()
        self._assert_managed_root(root)
        if not root.exists():
            return []
        candidates: list[Path] = []
        for child in root.iterdir():
            resolved_child = child.resolve()
            self._assert_child(root, resolved_child)
            if not resolved_child.is_dir():
                candidates.append(resolved_child)
                continue
            nested = [item.resolve() for item in resolved_child.iterdir()]
            nested_dirs = [item for item in nested if item.is_dir()]
            candidates.extend(nested_dirs or [resolved_child])

        cutoff = now - timedelta(days=retention_days)
        rows: list[dict[str, Any]] = []
        for candidate in candidates:
            self._assert_child(root, candidate)
            if self._contains_reference(candidate, referenced_paths):
                continue
            stat = candidate.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            if mtime > cutoff:
                continue
            rows.append(
                {
                    "kind": kind,
                    "path": str(candidate),
                    "relative_path": self._relative_storage_path(candidate),
                    "mtime": mtime.isoformat(),
                    "age_days": int((now - mtime).total_seconds() // 86400),
                    "bytes": self._path_size(candidate),
                }
            )
        return rows

    def _delete_candidate(self, path: Path) -> None:
        resolved = path.resolve()
        self._assert_managed_root(resolved)
        if resolved.is_dir():
            shutil.rmtree(resolved)
        elif resolved.is_file():
            resolved.unlink()
        else:
            raise StorageCleanupError("cleanup candidate no longer exists")

    def _assert_managed_root(self, path: Path) -> None:
        artifact_root = self.settings.artifact_root.resolve()
        workspace_root = self.settings.workspace_root.resolve()
        if path == artifact_root or artifact_root in path.parents:
            return
        if path == workspace_root or workspace_root in path.parents:
            return
        raise StorageCleanupError(f"refusing to manage path outside configured storage roots: {path}")

    @staticmethod
    def _assert_child(root: Path, path: Path) -> None:
        if path == root or root not in path.parents:
            raise StorageCleanupError(f"cleanup candidate escapes managed root: {path}")

    @staticmethod
    def _contains_reference(path: Path, referenced_paths: list[Path]) -> bool:
        for referenced in referenced_paths:
            if referenced == path or path in referenced.parents:
                return True
        return False

    @staticmethod
    def _resolved_existing(paths: Iterable[str | Path]) -> list[Path]:
        rows: list[Path] = []
        for path in paths:
            if not path:
                continue
            candidate = Path(path)
            try:
                rows.append(candidate.resolve())
            except OSError:
                continue
        return rows

    def _relative_storage_path(self, path: Path) -> str:
        artifact_root = self.settings.artifact_root.resolve()
        workspace_root = self.settings.workspace_root.resolve()
        if path == artifact_root or artifact_root in path.parents:
            return f"artifacts/{path.relative_to(artifact_root).as_posix()}"
        if path == workspace_root or workspace_root in path.parents:
            return f"workspaces/{path.relative_to(workspace_root).as_posix()}"
        return str(path)

    @staticmethod
    def _path_size(path: Path) -> int:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for child in path.rglob("*"):
            if child.is_file():
                with child.open("rb") as _:
                    total += child.stat().st_size
        return total

    @staticmethod
    def _root_summary(root: Path) -> dict[str, Any]:
        if not root.exists():
            return {"path": str(root), "exists": False, "files": 0, "dirs": 0, "bytes": 0}
        files = 0
        dirs = 0
        total = 0
        for child in root.rglob("*"):
            if child.is_dir():
                dirs += 1
            elif child.is_file():
                files += 1
                total += child.stat().st_size
        return {"path": str(root), "exists": True, "files": files, "dirs": dirs, "bytes": total}

    @staticmethod
    def _non_negative(value: int | None, fallback: int) -> int:
        selected = fallback if value is None else value
        return max(0, int(selected))

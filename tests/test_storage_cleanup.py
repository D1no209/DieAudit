from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

from app.services.storage_cleanup import StorageCleanupService


def make_settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        artifact_root=tmp_path / "artifacts",
        workspace_root=tmp_path / "workspaces",
        runtime_package_retention_days=7,
        upload_staging_retention_days=1,
        unreferenced_workspace_retention_days=30,
        unreferenced_snapshot_retention_days=90,
        storage_cleanup_max_entries=500,
    )


def touch_old(path: Path, *, age_days: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "payload.txt").write_text("payload", encoding="utf-8")
    timestamp = time.time() - age_days * 86400
    os.utime(path / "payload.txt", (timestamp, timestamp))
    os.utime(path, (timestamp, timestamp))


def test_storage_cleanup_dry_run_lists_expired_runtime_packages(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    old_package = settings.artifact_root / "runtime-packages" / "run-1"
    fresh_package = settings.artifact_root / "runtime-packages" / "run-2"
    touch_old(old_package, age_days=10)
    touch_old(fresh_package, age_days=1)
    service = StorageCleanupService(settings)

    result = service.cleanup(dry_run=True, policy=service.policy())

    assert result["deleted_count"] == 0
    assert [item["path"] for item in result["candidates"]] == [str(old_package.resolve())]
    assert old_package.exists()
    assert fresh_package.exists()


def test_storage_cleanup_deletes_selected_candidates(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    staged_upload = settings.artifact_root / "uploads" / "project-1"
    touch_old(staged_upload, age_days=3)
    service = StorageCleanupService(settings)

    result = service.cleanup(dry_run=False, policy=service.policy())

    assert result["deleted_count"] == 1
    assert not staged_upload.exists()


def test_storage_cleanup_preserves_referenced_workspace_and_snapshot(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    referenced_workspace = settings.workspace_root / "project-1" / "snapshot-1"
    stale_workspace = settings.workspace_root / "project-2" / "snapshot-2"
    referenced_archive = settings.artifact_root / "snapshots" / "project-1" / "snapshot-1" / "snapshot.tar.gz"
    stale_archive_dir = settings.artifact_root / "snapshots" / "project-2" / "snapshot-2"
    touch_old(referenced_workspace, age_days=45)
    touch_old(stale_workspace, age_days=45)
    referenced_archive.parent.mkdir(parents=True, exist_ok=True)
    referenced_archive.write_text("archive", encoding="utf-8")
    touch_old(stale_archive_dir, age_days=120)
    timestamp = time.time() - 120 * 86400
    os.utime(referenced_archive, (timestamp, timestamp))
    os.utime(referenced_archive.parent, (timestamp, timestamp))
    service = StorageCleanupService(settings)

    result = service.cleanup(
        dry_run=True,
        policy=service.policy(),
        referenced_workspace_paths=[referenced_workspace],
        referenced_snapshot_paths=[referenced_archive],
    )

    candidate_paths = {item["path"] for item in result["candidates"]}
    assert str(referenced_workspace.resolve()) not in candidate_paths
    assert str(referenced_archive.parent.resolve()) not in candidate_paths
    assert str(stale_workspace.resolve()) in candidate_paths
    assert str(stale_archive_dir.resolve()) in candidate_paths

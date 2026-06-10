from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.settings import Settings


class ArtifactAccessError(ValueError):
    pass


def resolve_artifact_path(settings: Settings, path: str | Path) -> Path:
    artifact_root = settings.artifact_root.resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = artifact_root / candidate
    resolved = candidate.resolve()
    if resolved != artifact_root and artifact_root not in resolved.parents:
        raise ArtifactAccessError("artifact path escapes artifact root")
    if not resolved.exists():
        raise FileNotFoundError("artifact not found")
    if not resolved.is_file():
        raise ArtifactAccessError("artifact path is not a file")
    return resolved


def artifact_metadata(settings: Settings, path: str | Path) -> dict[str, Any]:
    resolved = resolve_artifact_path(settings, path)
    stat = resolved.stat()
    artifact_root = settings.artifact_root.resolve()
    relative_path = resolved.relative_to(artifact_root).as_posix()
    return {
        "path": str(resolved),
        "relative_path": relative_path,
        "name": resolved.name,
        "size": stat.st_size,
        "updated_at": stat.st_mtime,
        "download_url": f"/artifacts/download?path={quote(relative_path)}",
    }


def artifact_path_matches(settings: Settings, stored_path: str | Path | None, requested_path: Path) -> bool:
    if not stored_path:
        return False
    try:
        return resolve_artifact_path(settings, stored_path) == requested_path.resolve()
    except (ArtifactAccessError, FileNotFoundError, OSError):
        return False


def secure_artifact_headers() -> dict[str, str]:
    return {
        "Cache-Control": "private, no-store, max-age=0",
        "Content-Security-Policy": "sandbox",
        "X-Content-Type-Options": "nosniff",
    }

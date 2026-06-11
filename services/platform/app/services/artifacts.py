from __future__ import annotations

import base64
import hashlib
import mimetypes
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
    artifact_id = artifact_id_for_relative_path(relative_path)
    return {
        "artifact_id": artifact_id,
        "artifact_uri": artifact_uri(settings, relative_path),
        "storage_backend": artifact_storage_backend(settings),
        "path": str(resolved),
        "relative_path": relative_path,
        "name": resolved.name,
        "size": stat.st_size,
        "sha256": file_sha256(resolved),
        "content_type": mimetypes.guess_type(resolved.name)[0] or "application/octet-stream",
        "updated_at": stat.st_mtime,
        "download_url": f"/artifacts/download?path={quote(relative_path)}",
        "canonical_download_url": f"/artifacts/{quote(artifact_id)}/download",
    }


def artifact_storage_backend(settings: Settings) -> str:
    return str(getattr(settings, "artifact_storage_backend", "local") or "local").strip().lower()


def artifact_uri(settings: Settings, relative_path: str) -> str:
    backend = artifact_storage_backend(settings)
    if backend == "minio":
        bucket = str(getattr(settings, "minio_bucket_artifacts", "dieaudit-artifacts") or "dieaudit-artifacts")
        return f"minio://{bucket}/{relative_path}"
    return f"local://artifacts/{relative_path}"


def artifact_id_for_relative_path(relative_path: str) -> str:
    normalized = relative_path.strip().replace("\\", "/")
    return base64.urlsafe_b64encode(normalized.encode("utf-8")).decode("ascii").rstrip("=")


def relative_path_for_artifact_id(artifact_id: str) -> str:
    padding = "=" * (-len(artifact_id) % 4)
    try:
        decoded = base64.urlsafe_b64decode((artifact_id + padding).encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise ArtifactAccessError("invalid artifact id") from exc
    if not decoded or decoded.startswith("/") or "\\" in decoded:
        raise ArtifactAccessError("invalid artifact id")
    return decoded


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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

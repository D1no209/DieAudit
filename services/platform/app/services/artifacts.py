from __future__ import annotations

import base64
import hashlib
import mimetypes
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.parse import quote

from app.settings import Settings


class ArtifactAccessError(ValueError):
    pass


@dataclass(frozen=True)
class ArtifactBlob:
    name: str
    content_type: str
    data: bytes


def resolve_artifact_path(settings: Settings, path: str | Path) -> Path:
    artifact_root = settings.artifact_root.resolve()
    resolved = artifact_absolute_path(settings, path)
    if not resolved.exists():
        raise FileNotFoundError("artifact not found")
    if not resolved.is_file():
        raise ArtifactAccessError("artifact path is not a file")
    return resolved


def artifact_absolute_path(settings: Settings, path: str | Path) -> Path:
    artifact_root = settings.artifact_root.resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = artifact_root / candidate
    resolved = candidate.resolve()
    if resolved != artifact_root and artifact_root not in resolved.parents:
        raise ArtifactAccessError("artifact path escapes artifact root")
    return resolved


def artifact_relative_path(settings: Settings, path: str | Path) -> str:
    resolved = artifact_absolute_path(settings, path)
    artifact_root = settings.artifact_root.resolve()
    try:
        return resolved.relative_to(artifact_root).as_posix()
    except ValueError as exc:
        raise ArtifactAccessError("artifact path escapes artifact root") from exc


def artifact_metadata(settings: Settings, path: str | Path) -> dict[str, Any]:
    return ArtifactStore(settings).metadata_for_path(path)


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


def bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact_path_matches(settings: Settings, stored_path: str | Path | None, requested_path: Path) -> bool:
    if not stored_path:
        return False
    try:
        return artifact_relative_path(settings, stored_path) == artifact_relative_path(settings, requested_path)
    except (ArtifactAccessError, OSError):
        return False


def secure_artifact_headers() -> dict[str, str]:
    return {
        "Cache-Control": "private, no-store, max-age=0",
        "Content-Security-Policy": "sandbox",
        "X-Content-Type-Options": "nosniff",
    }


class ArtifactStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.backend = artifact_storage_backend(settings)

    def metadata_for_path(self, path: str | Path) -> dict[str, Any]:
        relative_path = artifact_relative_path(self.settings, path)
        local_path = artifact_absolute_path(self.settings, relative_path)
        if local_path.exists():
            if not local_path.is_file():
                raise ArtifactAccessError("artifact path is not a file")
            return self._metadata_from_local(relative_path, local_path)
        if self.backend == "minio":
            return self._metadata_from_minio(relative_path)
        raise FileNotFoundError("artifact not found")

    def put_text(self, relative_path: str, text: str, *, content_type: str = "text/plain; charset=utf-8") -> dict[str, Any]:
        return self.put_bytes(relative_path, text.encode("utf-8"), content_type=content_type)

    def put_json(self, relative_path: str, payload: Any) -> dict[str, Any]:
        import json

        data = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return self.put_bytes(relative_path, data, content_type="application/json; charset=utf-8")

    def put_bytes(self, relative_path: str, data: bytes, *, content_type: str = "application/octet-stream") -> dict[str, Any]:
        normalized = self._validate_relative_path(relative_path)
        local_path = artifact_absolute_path(self.settings, normalized)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        metadata = self._metadata_from_local(normalized, local_path, content_type=content_type)
        if self.backend == "minio":
            self._upload_bytes(normalized, data, metadata)
        return metadata

    def upload_file(self, path: str | Path, *, content_type: str | None = None) -> dict[str, Any]:
        local_path = resolve_artifact_path(self.settings, path)
        relative_path = artifact_relative_path(self.settings, local_path)
        metadata = self._metadata_from_local(relative_path, local_path, content_type=content_type)
        if self.backend == "minio":
            self._upload_file(relative_path, local_path, metadata)
        return metadata

    def get_blob(self, path: str | Path) -> ArtifactBlob:
        relative_path = artifact_relative_path(self.settings, path)
        local_path = artifact_absolute_path(self.settings, relative_path)
        if self.backend == "minio":
            return self._download_minio(relative_path)
        if not local_path.exists():
            raise FileNotFoundError("artifact not found")
        if not local_path.is_file():
            raise ArtifactAccessError("artifact path is not a file")
        return ArtifactBlob(
            name=local_path.name,
            content_type=mimetypes.guess_type(local_path.name)[0] or "application/octet-stream",
            data=local_path.read_bytes(),
        )

    def _metadata_from_local(
        self,
        relative_path: str,
        local_path: Path,
        *,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        stat = local_path.stat()
        artifact_id = artifact_id_for_relative_path(relative_path)
        return {
            "artifact_id": artifact_id,
            "artifact_uri": artifact_uri(self.settings, relative_path),
            "storage_backend": self.backend,
            "path": str(local_path),
            "relative_path": relative_path,
            "name": local_path.name,
            "size": stat.st_size,
            "sha256": file_sha256(local_path),
            "content_type": content_type or mimetypes.guess_type(local_path.name)[0] or "application/octet-stream",
            "updated_at": stat.st_mtime,
            "download_url": f"/artifacts/download?path={quote(relative_path)}",
            "canonical_download_url": f"/artifacts/{quote(artifact_id)}/download",
        }

    def _metadata_from_minio(self, relative_path: str) -> dict[str, Any]:
        client = self._minio_client()
        try:
            stat = client.stat_object(self._bucket(), relative_path)
        except Exception as exc:
            raise FileNotFoundError("artifact not found") from exc
        metadata = {str(k).lower(): str(v) for k, v in (getattr(stat, "metadata", None) or {}).items()}
        sha256 = (
            metadata.get("x-amz-meta-sha256")
            or metadata.get("sha256")
            or metadata.get("x-minio-internal-sha256")
            or ""
        )
        content_type = getattr(stat, "content_type", None) or metadata.get("content-type") or "application/octet-stream"
        local_path = artifact_absolute_path(self.settings, relative_path)
        artifact_id = artifact_id_for_relative_path(relative_path)
        return {
            "artifact_id": artifact_id,
            "artifact_uri": artifact_uri(self.settings, relative_path),
            "storage_backend": self.backend,
            "path": str(local_path),
            "relative_path": relative_path,
            "name": local_path.name,
            "size": int(getattr(stat, "size", 0) or 0),
            "sha256": sha256,
            "content_type": content_type,
            "updated_at": getattr(getattr(stat, "last_modified", None), "timestamp", lambda: None)(),
            "download_url": f"/artifacts/download?path={quote(relative_path)}",
            "canonical_download_url": f"/artifacts/{quote(artifact_id)}/download",
        }

    def _upload_file(self, relative_path: str, local_path: Path, metadata: dict[str, Any]) -> None:
        client = self._minio_client()
        client.fput_object(
            self._bucket(),
            relative_path,
            str(local_path),
            content_type=metadata["content_type"],
            metadata={"sha256": metadata["sha256"]},
        )

    def _upload_bytes(self, relative_path: str, data: bytes, metadata: dict[str, Any]) -> None:
        client = self._minio_client()
        client.put_object(
            self._bucket(),
            relative_path,
            BytesIO(data),
            length=len(data),
            content_type=metadata["content_type"],
            metadata={"sha256": metadata["sha256"]},
        )

    def _download_minio(self, relative_path: str) -> ArtifactBlob:
        client = self._minio_client()
        try:
            response = client.get_object(self._bucket(), relative_path)
            try:
                data = response.read()
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:
            raise FileNotFoundError("artifact not found") from exc
        metadata = self._metadata_from_minio(relative_path)
        return ArtifactBlob(
            name=metadata["name"],
            content_type=metadata["content_type"],
            data=data,
        )

    def _bucket(self) -> str:
        return str(getattr(self.settings, "minio_bucket_artifacts", "dieaudit-artifacts") or "dieaudit-artifacts")

    def _minio_client(self):
        try:
            from minio import Minio
        except ImportError as exc:
            raise ArtifactAccessError("minio package is not installed") from exc

        raw_endpoint = str(getattr(self.settings, "minio_endpoint", "http://minio:9000") or "http://minio:9000")
        parsed = urlparse(raw_endpoint if "://" in raw_endpoint else f"http://{raw_endpoint}")
        endpoint = parsed.netloc or parsed.path
        secure = parsed.scheme == "https"
        return Minio(
            endpoint,
            access_key=str(getattr(self.settings, "minio_access_key", "") or ""),
            secret_key=str(getattr(self.settings, "minio_secret_key", "") or ""),
            secure=secure,
        )

    def _validate_relative_path(self, relative_path: str) -> str:
        normalized = relative_path.strip().replace("\\", "/")
        if not normalized or normalized.startswith("/") or "/../" in f"/{normalized}/":
            raise ArtifactAccessError("invalid artifact path")
        artifact_absolute_path(self.settings, normalized)
        return normalized

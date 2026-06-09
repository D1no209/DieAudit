from __future__ import annotations

import hashlib
import html
from html.parser import HTMLParser
from email import policy
from email.parser import BytesParser
from pathlib import Path
import re
from typing import Any, BinaryIO
import uuid

import httpx

from app.settings import Settings


COLLECTION_NAME = "dieaudit_knowledge_v1"
VECTOR_SIZE = 1024
CHUNK_TOKENS = 420
CHUNK_OVERLAP = 80


class KnowledgeIndexError(RuntimeError):
    pass


class KnowledgeService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.collection_name = COLLECTION_NAME
        self.vector_size = VECTOR_SIZE

    def save_upload(
        self,
        *,
        document_id: str,
        filename: str,
        stream: BinaryIO,
    ) -> Path:
        safe_name = _safe_filename(filename or "document.txt")
        target_dir = self.settings.artifact_root / "knowledge" / document_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / safe_name
        with target.open("wb") as handle:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                handle.write(chunk)
        return target

    def extract_text(self, path: Path, content_type: str | None = None) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf" or (content_type or "").lower() == "application/pdf":
            return _extract_pdf(path)
        if suffix in {".html", ".htm"} or "html" in (content_type or "").lower():
            return _html_to_text(path.read_text(encoding="utf-8", errors="replace"))
        if suffix in {".mhtml", ".mht"}:
            return _extract_mhtml(path)
        return path.read_text(encoding="utf-8", errors="replace")

    def chunk_text(self, text: str) -> list[str]:
        normalized = _normalize_text(text)
        tokens = normalized.split()
        if not tokens:
            return []
        chunks: list[str] = []
        step = max(CHUNK_TOKENS - CHUNK_OVERLAP, 1)
        for start in range(0, len(tokens), step):
            window = tokens[start : start + CHUNK_TOKENS]
            if not window:
                continue
            chunks.append(" ".join(window))
            if start + CHUNK_TOKENS >= len(tokens):
                break
        return chunks

    async def upsert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        await self.ensure_collection()
        points = []
        for chunk in chunks:
            points.append(
                {
                    "id": chunk["vector_id"],
                    "vector": embed_text(chunk["text"], self.vector_size),
                    "payload": {
                        "document_id": chunk["document_id"],
                        "chunk_id": chunk["chunk_id"],
                        "scope": chunk["scope"],
                        "project_id": chunk.get("project_id"),
                        "title": chunk.get("title"),
                        "source_name": chunk.get("source_name"),
                        "chunk_index": chunk["chunk_index"],
                    },
                }
            )
        async with httpx.AsyncClient(base_url=self.settings.qdrant_url, timeout=60) as client:
            response = await client.put(
                f"/collections/{self.collection_name}/points",
                json={"points": points, "wait": True},
            )
            if response.status_code >= 400:
                raise KnowledgeIndexError(response.text)

    async def search(self, *, query: str, project_id: str | None, include_global: bool, limit: int) -> list[dict[str, Any]]:
        await self.ensure_collection()
        scopes: list[tuple[str, str | None]] = []
        if project_id:
            scopes.append(("project", project_id))
        if include_global:
            scopes.append(("global", None))
        if not scopes:
            scopes.append(("global", None))
        per_scope = max(limit, 1)
        results: list[dict[str, Any]] = []
        async with httpx.AsyncClient(base_url=self.settings.qdrant_url, timeout=60) as client:
            for scope, scoped_project_id in scopes:
                response = await client.post(
                    f"/collections/{self.collection_name}/points/search",
                    json={
                        "vector": embed_text(query, self.vector_size),
                        "limit": per_scope,
                        "with_payload": True,
                        "filter": _qdrant_filter(scope, scoped_project_id),
                    },
                )
                if response.status_code == 404:
                    return []
                if response.status_code >= 400:
                    raise KnowledgeIndexError(response.text)
                for item in response.json().get("result", []):
                    payload = item.get("payload") or {}
                    results.append(
                        {
                            "score": item.get("score"),
                            "document_id": payload.get("document_id"),
                            "chunk_id": payload.get("chunk_id"),
                            "scope": payload.get("scope"),
                            "project_id": payload.get("project_id"),
                            "title": payload.get("title"),
                            "source_name": payload.get("source_name"),
                            "chunk_index": payload.get("chunk_index"),
                        }
                    )
        results.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return results[:limit]

    async def ensure_collection(self) -> None:
        async with httpx.AsyncClient(base_url=self.settings.qdrant_url, timeout=30) as client:
            response = await client.get(f"/collections/{self.collection_name}")
            if response.status_code == 200:
                return
            if response.status_code != 404:
                raise KnowledgeIndexError(response.text)
            create = await client.put(
                f"/collections/{self.collection_name}",
                json={"vectors": {"size": self.vector_size, "distance": "Cosine"}},
            )
            if create.status_code >= 400:
                raise KnowledgeIndexError(create.text)


def embed_text(text: str, size: int = VECTOR_SIZE) -> list[float]:
    vector = [0.0] * size
    tokens = _tokens(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % size
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    magnitude = sum(value * value for value in vector) ** 0.5
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w.\-:/#]+", text.lower())


def _normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _safe_filename(value: str) -> str:
    name = Path(value).name
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip(".-")
    return safe or f"document-{uuid.uuid4()}.txt"


def _qdrant_filter(scope: str, project_id: str | None) -> dict[str, Any]:
    must: list[dict[str, Any]] = [{"key": "scope", "match": {"value": scope}}]
    if project_id:
        must.append({"key": "project_id", "match": {"value": project_id}})
    return {"must": must}


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise KnowledgeIndexError("pypdf is not installed") from exc
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _extract_mhtml(path: Path) -> str:
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    parts = message.walk() if message.is_multipart() else [message]
    texts = []
    for part in parts:
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        payload = part.get_content()
        if isinstance(payload, bytes):
            payload = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        texts.append(_html_to_text(payload) if content_type == "text/html" else str(payload))
    return "\n".join(texts)


def _html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return parser.text()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._parts)

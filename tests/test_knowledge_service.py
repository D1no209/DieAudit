from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.api.routes import _delete_knowledge_artifact
from app.services.knowledge import KnowledgeService, embed_text


def test_chunk_rows_keep_project_scope_and_metadata(tmp_path: Path) -> None:
    service = KnowledgeService(SimpleNamespace(artifact_root=tmp_path, qdrant_url="http://qdrant:6333"))

    rows = service.chunk_rows(
        document_id="doc-1",
        title="SQL Injection Notes",
        source_name="article.md",
        scope="project",
        project_id="project-1",
        text="sql injection " * 500,
    )

    assert len(rows) >= 2
    assert rows[0]["document_id"] == "doc-1"
    assert rows[0]["project_id"] == "project-1"
    assert rows[0]["title"] == "SQL Injection Notes"
    assert rows[0]["source_name"] == "article.md"
    assert rows[0]["token_count"] > 0
    assert rows[0]["vector_id"] != rows[1]["vector_id"]


def test_embedding_is_normalized_and_stable() -> None:
    first = embed_text("SQL injection sink")
    second = embed_text("SQL injection sink")

    assert first == second
    assert abs(sum(value * value for value in first) - 1.0) < 0.000001


def test_delete_knowledge_artifact_removes_only_knowledge_document_dir(tmp_path: Path) -> None:
    settings = SimpleNamespace(artifact_root=tmp_path)
    document_dir = tmp_path / "knowledge" / "doc-1"
    document_dir.mkdir(parents=True)
    artifact = document_dir / "article.md"
    artifact.write_text("content", encoding="utf-8")

    assert _delete_knowledge_artifact(settings, artifact.resolve()) is True
    assert not document_dir.exists()


def test_delete_knowledge_artifact_refuses_paths_outside_knowledge_root(tmp_path: Path) -> None:
    settings = SimpleNamespace(artifact_root=tmp_path / "artifacts")
    outside = tmp_path / "outside.md"
    outside.write_text("content", encoding="utf-8")

    assert _delete_knowledge_artifact(settings, outside.resolve()) is False
    assert outside.exists()

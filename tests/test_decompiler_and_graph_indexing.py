from __future__ import annotations

from pathlib import Path

from app.api.routes import _codebase_memory_context, _render_structure_markdown
from app.services.decompiler import DecompilerService


def test_decompiler_records_packaged_artifact_when_tool_missing(tmp_path: Path) -> None:
    package = tmp_path / "app.jar"
    package.write_bytes(b"not really a jar")

    result = DecompilerService(tmp_path, max_artifacts=5).decompile()

    assert result["count"] == 1
    artifact = result["artifacts"][0]
    assert artifact["original_path"] == "app.jar"
    assert artifact["tool"] == "cfr"
    assert artifact["status"] in {"skipped", "failed", "completed"}
    assert artifact["workspace_output_path"].startswith(".dieaudit/decompiled/")


def test_structure_markdown_lists_decompiled_artifacts_and_graph_index_roots() -> None:
    markdown = _render_structure_markdown(
        audit_run_id="run-1",
        project_id="project-1",
        workspace_path="/workspace",
        inventory={
            "markers": ["pom.xml"],
            "top_directories": ["src"],
            "sample_files": ["src/App.java"],
            "critical_paths": {"routes": ["src/App.java"]},
        },
        decompiled={
            "artifacts": [
                {
                    "artifact_id": "app-abc",
                    "original_path": "target/app.jar",
                    "tool": "cfr",
                    "status": "completed",
                    "workspace_output_path": ".dieaudit/decompiled/app-abc",
                    "language_hint": "java",
                    "graph_indexable": True,
                }
            ]
        },
    )

    assert "## Architecture And Critical Flow Hints" in markdown
    assert "## Decompiled Artifacts" in markdown
    assert "## Recommended Code Graph Indexing" in markdown
    assert "`target/app.jar`" in markdown
    assert "`app-abc`" in markdown
    assert "codebase-memory-mcp.index_repository" in markdown


def test_codebase_memory_context_names_graph_tools() -> None:
    context = _codebase_memory_context()

    assert context["mcp"] == "codebase-memory-mcp"
    assert context["repo_path"] == "/workspace"
    assert "index_repository" in context["tools"]
    assert "get_architecture" in context["tools"]
    assert "trace_path" in context["tools"]

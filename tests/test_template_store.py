from __future__ import annotations

from pathlib import Path

import pytest

from app.services.templates import TemplateStore


def test_template_store_hides_demo_templates_by_default(tmp_path: Path) -> None:
    folder = tmp_path / "agent-templates"
    folder.mkdir()
    (folder / "agent-runtime-orchestrator.yaml").write_text(
        "name: agent-runtime-orchestrator\nimage: dieaudit/agent-runtime:local\n",
        encoding="utf-8",
    )
    (folder / "orchestrator.yaml").write_text(
        "name: orchestrator\nimage: dieaudit/mock-agent:local\nprotocol:\n  runtime: mock\n",
        encoding="utf-8",
    )

    store = TemplateStore(tmp_path, "agent-templates")

    assert [item["name"] for item in store.list()] == ["agent-runtime-orchestrator"]
    with pytest.raises(FileNotFoundError):
        store.get("orchestrator")


def test_template_store_can_include_demo_templates(tmp_path: Path) -> None:
    folder = tmp_path / "agent-templates"
    folder.mkdir()
    (folder / "orchestrator.yaml").write_text(
        "name: orchestrator\nimage: dieaudit/mock-agent:local\nprotocol:\n  runtime: mock\n",
        encoding="utf-8",
    )

    store = TemplateStore(tmp_path, "agent-templates", include_demo=True)

    assert [item["name"] for item in store.list()] == ["orchestrator"]
    assert store.get("orchestrator")["name"] == "orchestrator"

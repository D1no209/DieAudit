from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def worker_stage_names() -> list[str]:
    env = os.environ.copy()
    paths = [str(ROOT / "services/workflow-worker"), str(ROOT / "services/platform-common")]
    env["PYTHONPATH"] = os.pathsep.join(paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    script = (
        "import json;"
        "from app.pipeline.registry import StageRegistry;"
        "from app.pipeline.stages.default import default_stages;"
        "print(json.dumps([stage.name for stage in StageRegistry(default_stages()).ordered()]))"
    )
    output = subprocess.check_output(["python", "-c", script], cwd=ROOT, env=env, text=True)
    return json.loads(output)


def test_default_pipeline_registry_orders_dependencies_before_dependents() -> None:
    positions = {stage: index for index, stage in enumerate(worker_stage_names())}

    assert positions["snapshot-ready"] < positions["structure-discovery"]
    assert positions["structure-discovery"] < positions["agent-audit"]
    assert positions["agent-audit"] < positions["code-analysis"]
    assert positions["code-analysis"] < positions["value-triage"]
    assert positions["value-triage"] < positions["whiteboard-swarm"]
    assert positions["whiteboard-swarm"] < positions["validation-judgement"]
    assert positions["validation-judgement"] < positions["feedback-loop"]
    assert positions["feedback-loop"] < positions["poc-writing"]
    assert positions["poc-writing"] < positions["poc-verification"]
    assert positions["poc-verification"] < positions["report"]
    assert positions["report"] < positions["runtime-cleanup"]


def test_default_pipeline_registry_contains_planned_stage_names() -> None:
    names = worker_stage_names()

    assert names == [
        "snapshot-ready",
        "structure-discovery",
        "agent-audit",
        "code-analysis",
        "value-triage",
        "whiteboard-swarm",
        "validation-judgement",
        "feedback-loop",
        "poc-writing",
        "poc-verification",
        "report",
        "runtime-cleanup",
    ]

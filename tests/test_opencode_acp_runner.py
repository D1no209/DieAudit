from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _load_runner_module():
    schema = types.SimpleNamespace(
        RequestPermissionResponse=lambda **kwargs: kwargs,
        AllowedOutcome=lambda **kwargs: kwargs,
        DeniedOutcome=lambda **kwargs: kwargs,
    )
    acp = types.ModuleType("acp")
    acp.Client = object
    acp.schema = schema
    acp.PROTOCOL_VERSION = "test"
    acp.spawn_agent_process = None
    sys.modules["acp"] = acp
    sys.modules["acp.schema"] = schema

    path = Path(__file__).resolve().parents[1] / "services" / "agents" / "opencode-agent" / "opencode_acp_runner.py"
    spec = importlib.util.spec_from_file_location("opencode_acp_runner_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prompt_includes_current_finding_markdown() -> None:
    runner = _load_runner_module()

    prompt = runner._prompt(
        {
            "payload": {
                "goal": "validate",
                "finding_artifact_contract": {
                    "finding_markdown_path": "/finding/finding.md",
                    "agent_writable_report_path": "/artifacts/source-sink-report.md",
                },
            }
        },
        finding_markdown="# Finding\n\nPrior notes",
    )

    assert "Current `/finding/finding.md` content loaded by the runner" in prompt
    assert "Prior notes" in prompt
    assert "/artifacts/source-sink-report.md" in prompt


def test_permission_policy_allows_only_finding_and_artifact_paths() -> None:
    runner = _load_runner_module()
    options = [{"kind": "allow_once", "option_id": "once"}]

    assert (
        runner._allowed_permission_option(
            {"raw_input": {"filepath": "/finding/finding.md", "parentDir": "/finding"}},
            options,
        )
        == "once"
    )
    assert (
        runner._allowed_permission_option(
            {"raw_input": {"filepath": "/artifacts/source-sink-report.md", "parentDir": "/artifacts"}},
            options,
        )
        == "once"
    )
    assert (
        runner._allowed_permission_option(
            {"raw_input": {"filepath": "/dieaudit/artifacts/findings/run/finding/poc/poc.md"}},
            options,
        )
        == "once"
    )
    assert runner._allowed_permission_option({"raw_input": {"filepath": "/workspace/app.py"}}, options) is None
    assert runner._allowed_permission_option({"raw_input": {"filepath": "/etc/passwd"}}, options) is None


def test_event_transcript_joins_agent_chunks_in_order() -> None:
    runner = _load_runner_module()

    transcript = runner._extract_event_transcript(
        [
            {
                "update": {
                    "session_update": "agent_thought_chunk",
                    "content": {"text": "Source"},
                }
            },
            {
                "update": {
                    "session_update": "agent_thought_chunk",
                    "content": {"text": "-Sink"},
                }
            },
            {
                "update": {
                    "session_update": "tool_call_update",
                    "content": {"text": "ignored"},
                }
            },
        ]
    )

    assert transcript == "Source-Sink"

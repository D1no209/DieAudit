from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_web_ui_does_not_request_weak_sandbox_isolation_by_default() -> None:
    app_source = (ROOT / "services/web-ui/src/App.tsx").read_text(encoding="utf-8")

    assert "allow_weak_isolation: true" not in app_source

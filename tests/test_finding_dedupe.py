from __future__ import annotations

from app.services.finding_dedupe import finding_identity, optional_int


def test_finding_identity_normalizes_core_fields() -> None:
    identity = finding_identity(
        title="X" * 300,
        source="semgrep-mcp",
        file_path="src/app.py",
        line_start="42",
        rule_id="python.flask.security",
    )

    assert identity == {
        "title": "X" * 255,
        "source": "semgrep-mcp",
        "file_path": "src/app.py",
        "line_start": 42,
        "rule_id": "python.flask.security",
    }


def test_finding_identity_handles_missing_optional_location_fields() -> None:
    identity = finding_identity(
        title="Dependency vulnerability",
        source="sca-mcp",
        file_path="",
        line_start="not-a-number",
    )

    assert identity["file_path"] is None
    assert identity["line_start"] is None
    assert identity["rule_id"] is None
    assert optional_int("") is None

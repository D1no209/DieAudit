from __future__ import annotations

from app.services.agent_output import AgentOutputIngestor


def test_extract_structured_payload_reports_not_found() -> None:
    ingestor = AgentOutputIngestor()

    structured, warnings = ingestor._extract_structured_payload({"message": "plain text only"})

    assert structured == {}
    assert ingestor._parse_status(structured, warnings) == "not_found"
    assert warnings == [{"kind": "structured_output_not_found"}]


def test_extract_structured_payload_parses_json_from_text() -> None:
    ingestor = AgentOutputIngestor()

    structured, warnings = ingestor._extract_structured_payload(
        {"message": 'result:\n```json\n{"findings": [], "evidence": [], "summary": "ok"}\n```'}
    )

    assert structured["findings"] == []
    assert structured["evidence"] == []
    assert ingestor._parse_status(structured, warnings) == "parsed"


def test_parse_status_marks_structured_warnings() -> None:
    ingestor = AgentOutputIngestor()

    assert ingestor._parse_status({"findings": []}, [{"kind": "finding_missing_fields"}]) == "parsed_with_warnings"


def test_normalize_finding_item_defaults_missing_confidence() -> None:
    ingestor = AgentOutputIngestor()
    warnings = []

    item = ingestor._normalize_finding_item(
        {
            "title": "Path traversal",
            "severity": "high",
            "file_path": "app.py",
            "line_start": 7,
            "description": "Untrusted path reaches open().",
            "source": "agent",
        },
        index=0,
        warnings=warnings,
    )

    assert item["confidence"] == "medium"
    assert warnings == [{"kind": "finding_defaulted_confidence", "index": 0, "value": "medium", "reason": "agent omitted confidence"}]

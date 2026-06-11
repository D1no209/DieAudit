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

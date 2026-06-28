from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.runtime import WhiteboardLinkCandidateInput
from app.domain.models import WhiteboardEvent, WhiteboardSubscription
from app.services.whiteboard import WhiteboardService


def test_whiteboard_link_candidates_require_card_ids_array() -> None:
    result = WhiteboardService._normalize_link_candidates(
        [
            {
                "title": "entrypoint candidates",
                "card_ids": ["card-1", "card-2"],
                "status": "Finding",
                "agent_run_id": "agent-1",
            },
            {"title": "blocked path", "card_ids": [], "status": "Impossible"},
            {"title": "legacy ignored", "card_id": "old-card", "status": "Hint"},
        ]
    )

    assert result[0]["card_ids"] == ["card-1", "card-2"]
    assert result[0]["status"] == "finding"
    assert result[0]["agent_run_id"] == "agent-1"
    assert result[1]["status"] == "impossible"
    assert "old-card" not in result[2]["card_ids"]


def test_whiteboard_link_candidate_schema_rejects_card_id() -> None:
    with pytest.raises(ValidationError):
        WhiteboardLinkCandidateInput(card_id="old-card", status="hint")


def test_whiteboard_subscription_matches_card_type_and_keyword() -> None:
    subscription = WhiteboardSubscription(
        subscription_id="sub-1",
        audit_run_id="run-1",
        project_id="project-1",
        subscriber_agent_run_id="agent-1",
        filter_json={"card_types": ["sink"], "keywords": ["deserialize"]},
        status="active",
    )
    event = WhiteboardEvent(
        event_id="event-1",
        audit_run_id="run-1",
        project_id="project-1",
        entity_type="card",
        entity_id="card-1",
        event_type="created",
        summary="deserialize sink candidate",
        payload={"card": {"card_type": "sink", "status": "open", "title": "deserialize"}},
    )

    assert WhiteboardService._subscription_matches(subscription, event)


def test_whiteboard_subscription_rejects_non_matching_status() -> None:
    subscription = WhiteboardSubscription(
        subscription_id="sub-1",
        audit_run_id="run-1",
        project_id="project-1",
        subscriber_agent_run_id="agent-1",
        filter_json={"statuses": ["ready"]},
        status="active",
    )
    event = WhiteboardEvent(
        event_id="event-1",
        audit_run_id="run-1",
        project_id="project-1",
        entity_type="card",
        entity_id="card-1",
        event_type="updated",
        summary="card updated",
        payload={"card": {"card_type": "sink", "status": "open"}},
    )

    assert not WhiteboardService._subscription_matches(subscription, event)

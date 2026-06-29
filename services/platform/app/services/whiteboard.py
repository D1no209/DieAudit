from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    AuditRun,
    Evidence,
    FindingTriageDecision,
    WhiteboardAttachment,
    WhiteboardCard,
    WhiteboardEdge,
    WhiteboardEvent,
    WhiteboardNotification,
    WhiteboardNote,
    WhiteboardScheduleRequest,
    WhiteboardSubscription,
    WhiteboardTask,
)
from app.services.artifacts import ArtifactStore
from app.settings import Settings


WHITEBOARD_EDGE_TYPES = {"precedes", "supports", "contradicts", "duplicates", "blocks", "refines"}
WHITEBOARD_LINK_STATUSES = {"not_ready", "finding", "not_found", "hint", "impossible"}
WHITEBOARD_AGENT_BY_GAP_TYPE = {
    "source": ("source-sink-finder", "kimi-source-sink-finder"),
    "predecessor": ("source-sink-finder", "kimi-source-sink-finder"),
    "successor": ("source-sink-finder", "kimi-source-sink-finder"),
    "validation": ("validator", "kimi-validator"),
    "judgement": ("judger", "kimi-judger"),
    "poc": ("poc-writer", "kimi-poc-writer"),
    "poc-verification": ("poc-verifier", "kimi-poc-verifier"),
}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _whiteboard_attachment_to_dict(row: WhiteboardAttachment) -> dict[str, Any]:
    return {
        "attachment_id": row.attachment_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "card_id": row.card_id,
        "path": row.path,
        "label": row.label,
        "content_type": row.content_type,
        "metadata": row.metadata_json or {},
        "created_at": _iso(row.created_at),
    }


def _whiteboard_card_to_dict(row: WhiteboardCard, *, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "card_id": row.card_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "title": row.title,
        "card_type": row.card_type,
        "status": row.status,
        "author": row.author,
        "agent_run_id": row.agent_run_id,
        "event_time": _iso(row.event_time),
        "content": row.content,
        "confidence": row.confidence,
        "finding_id": row.finding_id,
        "file_path": row.file_path,
        "line_start": row.line_start,
        "line_end": row.line_end,
        "expected_predecessors": row.expected_predecessors or [],
        "possible_successors": row.possible_successors or [],
        "requirements": row.requirements or [],
        "metadata": row.metadata_json or {},
        "attachments": attachments or [],
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _whiteboard_edge_to_dict(row: WhiteboardEdge) -> dict[str, Any]:
    return {
        "edge_id": row.edge_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "source_card_id": row.source_card_id,
        "target_card_id": row.target_card_id,
        "edge_type": row.edge_type,
        "author": row.author,
        "agent_run_id": row.agent_run_id,
        "rationale": row.rationale,
        "metadata": row.metadata_json or {},
        "created_at": _iso(row.created_at),
    }


def _whiteboard_note_to_dict(row: WhiteboardNote) -> dict[str, Any]:
    return {
        "note_id": row.note_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "card_id": row.card_id,
        "author": row.author,
        "agent_run_id": row.agent_run_id,
        "content": row.content,
        "metadata": row.metadata_json or {},
        "created_at": _iso(row.created_at),
    }


def _whiteboard_task_to_dict(row: WhiteboardTask) -> dict[str, Any]:
    return {
        "task_id": row.task_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "gap_card_id": row.gap_card_id,
        "card_id": row.card_id,
        "agent_role": row.agent_role,
        "agent_name": row.agent_name,
        "agent_run_id": row.agent_run_id,
        "parent_task_id": row.parent_task_id,
        "root_task_id": row.root_task_id,
        "wait_reason": row.wait_reason,
        "wake_event_id": row.wake_event_id,
        "task_group": row.task_group,
        "requested_by_agent_run_id": row.requested_by_agent_run_id,
        "status": row.status,
        "round_index": row.round_index,
        "attempt_index": row.attempt_index,
        "prompt": row.prompt,
        "result": row.result or {},
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _whiteboard_event_to_dict(row: WhiteboardEvent) -> dict[str, Any]:
    return {
        "event_id": row.event_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "event_type": row.event_type,
        "summary": row.summary,
        "payload": row.payload or {},
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _whiteboard_subscription_to_dict(row: WhiteboardSubscription) -> dict[str, Any]:
    return {
        "subscription_id": row.subscription_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "subscriber_task_id": row.subscriber_task_id,
        "subscriber_agent_run_id": row.subscriber_agent_run_id,
        "filter": row.filter_json or {},
        "cursor_event_id": row.cursor_event_id,
        "status": row.status,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _whiteboard_notification_to_dict(row: WhiteboardNotification) -> dict[str, Any]:
    return {
        "notification_id": row.notification_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "event_id": row.event_id,
        "subscription_id": row.subscription_id,
        "subscriber_task_id": row.subscriber_task_id,
        "subscriber_agent_run_id": row.subscriber_agent_run_id,
        "status": row.status,
        "claimed_by_agent_run_id": row.claimed_by_agent_run_id,
        "lease_expires_at": _iso(row.lease_expires_at),
        "attempt_count": row.attempt_count,
        "summary": row.summary,
        "payload": row.payload or {},
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _whiteboard_schedule_request_to_dict(row: WhiteboardScheduleRequest) -> dict[str, Any]:
    return {
        "request_id": row.request_id,
        "audit_run_id": row.audit_run_id,
        "project_id": row.project_id,
        "requested_by_task_id": row.requested_by_task_id,
        "requested_by_agent_run_id": row.requested_by_agent_run_id,
        "suggested_agent_name": row.suggested_agent_name,
        "goal": row.goal,
        "reason": row.reason,
        "related_card_ids": row.related_card_ids or [],
        "status": row.status,
        "decision": row.decision or {},
        "task_id": row.task_id,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


class WhiteboardService:
    def __init__(self, settings: Settings, session: AsyncSession):
        self.settings = settings
        self.session = session
        self.artifacts = ArtifactStore(settings)

    async def graph(self, audit_run_id: str) -> dict[str, Any]:
        audit_run = await self._audit_run(audit_run_id)
        attachments = (
            await self.session.execute(select(WhiteboardAttachment).where(WhiteboardAttachment.audit_run_id == audit_run_id))
        ).scalars().all()
        attachment_map: dict[str, list[dict[str, Any]]] = {}
        for item in attachments:
            attachment_map.setdefault(item.card_id, []).append(_whiteboard_attachment_to_dict(item))
        cards = (
            await self.session.execute(select(WhiteboardCard).where(WhiteboardCard.audit_run_id == audit_run_id).order_by(WhiteboardCard.created_at.asc()))
        ).scalars().all()
        edges = (
            await self.session.execute(select(WhiteboardEdge).where(WhiteboardEdge.audit_run_id == audit_run_id).order_by(WhiteboardEdge.created_at.asc()))
        ).scalars().all()
        notes = (
            await self.session.execute(select(WhiteboardNote).where(WhiteboardNote.audit_run_id == audit_run_id).order_by(WhiteboardNote.created_at.asc()))
        ).scalars().all()
        tasks = (
            await self.session.execute(select(WhiteboardTask).where(WhiteboardTask.audit_run_id == audit_run_id).order_by(WhiteboardTask.created_at.asc()))
        ).scalars().all()
        events = (
            await self.session.execute(select(WhiteboardEvent).where(WhiteboardEvent.audit_run_id == audit_run_id).order_by(WhiteboardEvent.created_at.desc()).limit(100))
        ).scalars().all()
        subscriptions = (
            await self.session.execute(select(WhiteboardSubscription).where(WhiteboardSubscription.audit_run_id == audit_run_id).order_by(WhiteboardSubscription.created_at.asc()))
        ).scalars().all()
        notifications = (
            await self.session.execute(select(WhiteboardNotification).where(WhiteboardNotification.audit_run_id == audit_run_id).order_by(WhiteboardNotification.created_at.desc()).limit(100))
        ).scalars().all()
        schedule_requests = (
            await self.session.execute(select(WhiteboardScheduleRequest).where(WhiteboardScheduleRequest.audit_run_id == audit_run_id).order_by(WhiteboardScheduleRequest.created_at.desc()).limit(100))
        ).scalars().all()
        evidence_rows = (
            await self.session.execute(
                select(Evidence)
                .where(Evidence.audit_run_id == audit_run_id)
                .where(Evidence.kind == "whiteboard-chain")
                .order_by(Evidence.created_at.asc())
            )
        ).scalars().all()
        return {
            "audit_run_id": audit_run_id,
            "project_id": audit_run.project_id,
            "snapshot": self._snapshot_path(audit_run_id),
            "cards": [_whiteboard_card_to_dict(row, attachments=attachment_map.get(row.card_id, [])) for row in cards],
            "edges": [_whiteboard_edge_to_dict(row) for row in edges],
            "notes": [_whiteboard_note_to_dict(row) for row in notes],
            "tasks": [_whiteboard_task_to_dict(row) for row in tasks],
            "events": [_whiteboard_event_to_dict(row) for row in events],
            "subscriptions": [_whiteboard_subscription_to_dict(row) for row in subscriptions],
            "notifications": [_whiteboard_notification_to_dict(row) for row in notifications],
            "schedule_requests": [_whiteboard_schedule_request_to_dict(row) for row in schedule_requests],
            "evidence": [
                {
                    "evidence_id": row.evidence_id,
                    "finding_id": row.finding_id,
                    "summary": row.summary,
                    "artifact_path": row.artifact_path,
                    "payload": row.payload or {},
                    "created_at": _iso(row.created_at),
                }
                for row in evidence_rows
            ],
        }

    async def create_card(self, audit_run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        audit_run = await self._audit_run(audit_run_id)
        card = WhiteboardCard(
            card_id=str(uuid.uuid4()),
            audit_run_id=audit_run_id,
            project_id=audit_run.project_id,
            title=str(body.get("title") or "").strip(),
            card_type=self._safe_token(body.get("card_type") or "observation", "observation"),
            status=self._safe_token(body.get("status") or "open", "open"),
            author=self._optional_str(body.get("author"), 255),
            agent_run_id=self._optional_str(body.get("agent_run_id"), 128),
            event_time=self._parse_event_time(body.get("event_time")),
            content=self._optional_str(body.get("content"), 20000),
            confidence=self._optional_str(body.get("confidence"), 32),
            finding_id=self._optional_str(body.get("finding_id"), 128),
            file_path=self._optional_str(body.get("file_path"), 2048),
            line_start=body.get("line_start"),
            line_end=body.get("line_end"),
            expected_predecessors=self._normalize_link_candidates(body.get("expected_predecessors")),
            possible_successors=self._normalize_link_candidates(body.get("possible_successors")),
            requirements=[str(item)[:500] for item in body.get("requirements") or []],
            metadata_json=dict(body.get("metadata") or {}),
        )
        if not card.title:
            raise ValueError("title is required")
        self.session.add(card)
        await self.session.flush()
        for attachment in body.get("attachments") or []:
            await self.add_attachment(audit_run_id, card.card_id, attachment, flush=False)
        await self.record_event(
            audit_run_id,
            entity_type="card",
            entity_id=card.card_id,
            event_type="created",
            summary=f"Card created: {card.title}",
            payload={"card": _whiteboard_card_to_dict(card)},
            project_id=audit_run.project_id,
        )
        await self.session.commit()
        await self.write_snapshot(audit_run_id)
        return await self.card(audit_run_id, card.card_id)

    async def card(self, audit_run_id: str, card_id: str) -> dict[str, Any]:
        card = await self._card(audit_run_id, card_id)
        attachments = (
            await self.session.execute(select(WhiteboardAttachment).where(WhiteboardAttachment.audit_run_id == audit_run_id, WhiteboardAttachment.card_id == card_id))
        ).scalars().all()
        return _whiteboard_card_to_dict(card, attachments=[_whiteboard_attachment_to_dict(item) for item in attachments])

    async def update_card(self, audit_run_id: str, card_id: str, body: dict[str, Any]) -> dict[str, Any]:
        card = await self._card(audit_run_id, card_id)
        for field in ("title", "card_type", "status", "content", "confidence"):
            if field in body and body[field] is not None:
                setattr(card, field, str(body[field])[:20000] if field == "content" else str(body[field])[:255])
        for field in ("expected_predecessors", "possible_successors", "requirements"):
            if field in body and body[field] is not None:
                value = self._normalize_link_candidates(body[field]) if field in {"expected_predecessors", "possible_successors"} else list(body[field])
                setattr(card, field, value)
        if body.get("metadata") is not None:
            card.metadata_json = dict(body.get("metadata") or {})
        await self.record_event(
            audit_run_id,
            entity_type="card",
            entity_id=card.card_id,
            event_type="updated",
            summary=f"Card updated: {card.title}",
            payload={"updates": body, "card": _whiteboard_card_to_dict(card)},
            project_id=card.project_id,
        )
        await self.session.commit()
        await self.write_snapshot(audit_run_id)
        return await self.card(audit_run_id, card_id)

    async def create_edge(self, audit_run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        audit_run = await self._audit_run(audit_run_id)
        source_id = str(body.get("source_card_id") or "")
        target_id = str(body.get("target_card_id") or "")
        if source_id == target_id:
            raise ValueError("source_card_id and target_card_id must differ")
        await self._card(audit_run_id, source_id)
        await self._card(audit_run_id, target_id)
        edge_type = self._safe_token(body.get("edge_type") or "supports", "supports")
        if edge_type not in WHITEBOARD_EDGE_TYPES:
            raise ValueError(f"edge_type must be one of {sorted(WHITEBOARD_EDGE_TYPES)}")
        edge = WhiteboardEdge(
            edge_id=str(uuid.uuid4()),
            audit_run_id=audit_run_id,
            project_id=audit_run.project_id,
            source_card_id=source_id,
            target_card_id=target_id,
            edge_type=edge_type,
            author=self._optional_str(body.get("author"), 255),
            agent_run_id=self._optional_str(body.get("agent_run_id"), 128),
            rationale=self._optional_str(body.get("rationale"), 10000),
            metadata_json=dict(body.get("metadata") or {}),
        )
        self.session.add(edge)
        await self.record_event(
            audit_run_id,
            entity_type="edge",
            entity_id=edge.edge_id,
            event_type="created",
            summary=f"Cards linked: {source_id} -> {target_id}",
            payload={"edge": _whiteboard_edge_to_dict(edge)},
            project_id=audit_run.project_id,
        )
        await self.session.commit()
        await self.write_snapshot(audit_run_id)
        return _whiteboard_edge_to_dict(edge)

    async def add_note(self, audit_run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        audit_run = await self._audit_run(audit_run_id)
        card_id = self._optional_str(body.get("card_id"), 128)
        if card_id:
            await self._card(audit_run_id, card_id)
        note = WhiteboardNote(
            note_id=str(uuid.uuid4()),
            audit_run_id=audit_run_id,
            project_id=audit_run.project_id,
            card_id=card_id,
            author=self._optional_str(body.get("author"), 255),
            agent_run_id=self._optional_str(body.get("agent_run_id"), 128),
            content=str(body.get("content") or "").strip(),
            metadata_json=dict(body.get("metadata") or {}),
        )
        if not note.content:
            raise ValueError("content is required")
        self.session.add(note)
        await self.record_event(
            audit_run_id,
            entity_type="note",
            entity_id=note.note_id,
            event_type="created",
            summary=f"Note added{f' to {card_id}' if card_id else ''}",
            payload={"note": _whiteboard_note_to_dict(note), "card_id": card_id},
            project_id=audit_run.project_id,
        )
        await self.session.commit()
        await self.write_snapshot(audit_run_id)
        return _whiteboard_note_to_dict(note)

    async def add_attachment(self, audit_run_id: str, card_id: str, body: dict[str, Any], *, flush: bool = True) -> dict[str, Any]:
        audit_run = await self._audit_run(audit_run_id)
        await self._card(audit_run_id, card_id)
        path = self._validate_attachment_path(str(body.get("path") or ""))
        attachment = WhiteboardAttachment(
            attachment_id=str(uuid.uuid4()),
            audit_run_id=audit_run_id,
            project_id=audit_run.project_id,
            card_id=card_id,
            path=path,
            label=self._optional_str(body.get("label"), 255),
            content_type=self._optional_str(body.get("content_type"), 255),
            metadata_json=dict(body.get("metadata") or {}),
        )
        self.session.add(attachment)
        if flush:
            await self.record_event(
                audit_run_id,
                entity_type="attachment",
                entity_id=attachment.attachment_id,
                event_type="created",
                summary=f"Attachment added: {path}",
                payload={"attachment": _whiteboard_attachment_to_dict(attachment), "card_id": card_id},
                project_id=audit_run.project_id,
            )
            await self.session.commit()
            await self.write_snapshot(audit_run_id)
        return _whiteboard_attachment_to_dict(attachment)

    async def declare_gap(self, audit_run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        body = dict(body)
        body["card_type"] = "gap"
        body.setdefault("status", "open")
        body.setdefault("title", body.get("title") or "Whiteboard gap")
        return await self.create_card(audit_run_id, body)

    async def submit_chain_evidence(self, audit_run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        audit_run = await self._audit_run(audit_run_id)
        card_ids = [str(item) for item in body.get("card_ids") or []]
        edge_ids = [str(item) for item in body.get("edge_ids") or []]
        cards = [await self._card(audit_run_id, card_id) for card_id in card_ids]
        edges = [await self._edge(audit_run_id, edge_id) for edge_id in edge_ids]
        finding_id = str(body.get("finding_id") or (cards[0].finding_id if cards else "") or "")
        if not finding_id:
            finding_id = "whiteboard"
        summary = str(body.get("summary") or self._evidence_summary(cards)).strip() or "Whiteboard chain evidence"
        graph = await self.graph(audit_run_id)
        metadata = self.artifacts.put_json(f"whiteboards/{audit_run_id}/evidence-{uuid.uuid4().hex[:12]}.json", {"summary": summary, "card_ids": card_ids, "edge_ids": edge_ids, "graph": graph})
        evidence = Evidence(
            evidence_id=str(uuid.uuid4()),
            finding_id=finding_id,
            audit_run_id=audit_run_id,
            kind="whiteboard-chain",
            summary=summary,
            artifact_path=metadata["relative_path"],
            payload={"card_ids": card_ids, "edge_ids": edge_ids, "source": "whiteboard"},
        )
        self.session.add(evidence)
        if body.get("mark_cards_submitted", True):
            for card in cards:
                card.status = "submitted"
        await self.record_event(
            audit_run_id,
            entity_type="evidence",
            entity_id=evidence.evidence_id,
            event_type="created",
            summary=summary,
            payload={"card_ids": card_ids, "edge_ids": edge_ids, "evidence_id": evidence.evidence_id},
            project_id=audit_run.project_id,
        )
        await self.session.commit()
        await self.write_snapshot(audit_run_id)
        return {"ok": True, "evidence_id": evidence.evidence_id, "artifact": metadata, "summary": summary}

    async def search_cards(self, audit_run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        await self._audit_run(audit_run_id)
        query = str(body.get("query") or "").strip().lower()
        terms = [term for term in query.replace("\\", "/").split() if term]
        card_type = self._optional_str(body.get("card_type"), 64)
        status = self._optional_str(body.get("status"), 64)
        finding_id = self._optional_str(body.get("finding_id"), 128)
        file_path = self._optional_str(body.get("file_path"), 2048)
        candidate_status = self._optional_str(body.get("candidate_status"), 32)
        limit = max(1, min(int(body.get("limit") or 20), 100))
        rows = (
            await self.session.execute(select(WhiteboardCard).where(WhiteboardCard.audit_run_id == audit_run_id).order_by(WhiteboardCard.updated_at.desc()))
        ).scalars().all()
        matches: list[dict[str, Any]] = []
        for row in rows:
            reasons: list[str] = []
            if card_type and row.card_type != card_type:
                continue
            if status and row.status != status:
                continue
            if finding_id and row.finding_id != finding_id:
                continue
            if file_path and file_path not in str(row.file_path or ""):
                continue
            if candidate_status and not self._card_has_candidate_status(row, candidate_status):
                continue
            haystack = " ".join(
                [
                    row.title or "",
                    row.content or "",
                    row.finding_id or "",
                    row.file_path or "",
                    row.card_type or "",
                    row.status or "",
                    " ".join(str(item.get("title") or "") for item in row.expected_predecessors or [] if isinstance(item, dict)),
                    " ".join(str(item.get("title") or "") for item in row.possible_successors or [] if isinstance(item, dict)),
                ]
            ).lower()
            score = 0
            for term in terms:
                if term in haystack:
                    score += 1
                    reasons.append(f"matched:{term}")
            if terms and score == 0:
                continue
            if card_type:
                reasons.append(f"card_type:{card_type}")
            if status:
                reasons.append(f"status:{status}")
            if finding_id:
                reasons.append(f"finding_id:{finding_id}")
            if file_path:
                reasons.append(f"file_path:{file_path}")
            if candidate_status:
                reasons.append(f"candidate_status:{candidate_status}")
            matches.append({"score": score, "reasons": reasons or ["filter"], "card": _whiteboard_card_to_dict(row)})
        matches.sort(key=lambda item: (-int(item["score"]), str((item["card"] or {}).get("updated_at") or "")), reverse=False)
        return {"query": body, "count": len(matches[:limit]), "matches": matches[:limit]}

    async def list_events(self, audit_run_id: str, *, limit: int = 100, after_event_id: str | None = None) -> list[dict[str, Any]]:
        await self._audit_run(audit_run_id)
        rows = (
            await self.session.execute(
                select(WhiteboardEvent)
                .where(WhiteboardEvent.audit_run_id == audit_run_id)
                .order_by(WhiteboardEvent.created_at.asc())
            )
        ).scalars().all()
        if after_event_id:
            seen = False
            filtered = []
            for row in rows:
                if seen:
                    filtered.append(row)
                elif row.event_id == after_event_id:
                    seen = True
            rows = filtered
        return [_whiteboard_event_to_dict(row) for row in rows[-max(1, min(limit, 500)):]]

    async def subscribe(self, audit_run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        audit_run = await self._audit_run(audit_run_id)
        subscriber_task_id = self._optional_str(body.get("subscriber_task_id") or body.get("task_id"), 128)
        subscriber_agent_run_id = self._optional_str(body.get("subscriber_agent_run_id") or body.get("agent_run_id"), 128)
        if not subscriber_task_id and not subscriber_agent_run_id:
            raise ValueError("subscriber_task_id or subscriber_agent_run_id is required")
        row = WhiteboardSubscription(
            subscription_id=str(uuid.uuid4()),
            audit_run_id=audit_run_id,
            project_id=audit_run.project_id,
            subscriber_task_id=subscriber_task_id,
            subscriber_agent_run_id=subscriber_agent_run_id,
            filter_json=dict(body.get("filter") or {}),
            cursor_event_id=self._optional_str(body.get("cursor_event_id"), 128),
            status=self._safe_token(body.get("status") or "active", "active"),
        )
        self.session.add(row)
        await self.session.commit()
        return _whiteboard_subscription_to_dict(row)

    async def list_notifications(self, audit_run_id: str, *, status: str | None = None, subscriber_agent_run_id: str | None = None) -> list[dict[str, Any]]:
        await self._audit_run(audit_run_id)
        stmt = select(WhiteboardNotification).where(WhiteboardNotification.audit_run_id == audit_run_id)
        if status:
            stmt = stmt.where(WhiteboardNotification.status == status)
        if subscriber_agent_run_id:
            stmt = stmt.where(WhiteboardNotification.subscriber_agent_run_id == subscriber_agent_run_id)
        rows = (await self.session.execute(stmt.order_by(WhiteboardNotification.created_at.desc()).limit(200))).scalars().all()
        return [_whiteboard_notification_to_dict(row) for row in rows]

    async def update_notification(self, audit_run_id: str, notification_id: str, status: str, *, claimed_by_agent_run_id: str | None = None, lease_seconds: int | None = None) -> dict[str, Any]:
        await self._audit_run(audit_run_id)
        row = await self.session.scalar(
            select(WhiteboardNotification).where(
                WhiteboardNotification.audit_run_id == audit_run_id,
                WhiteboardNotification.notification_id == notification_id,
            )
        )
        if not row:
            raise LookupError("whiteboard notification not found")
        normalized = self._safe_token(status, "pending")
        if normalized not in {"pending", "claimed", "handled", "ignored"}:
            raise ValueError("notification status must be pending, claimed, handled, or ignored")
        row.status = normalized
        if normalized == "claimed":
            row.claimed_by_agent_run_id = self._optional_str(claimed_by_agent_run_id, 128) or row.subscriber_agent_run_id
            row.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(30, int(lease_seconds or 300)))
            row.attempt_count = int(row.attempt_count or 0) + 1
        elif normalized in {"handled", "ignored"}:
            row.lease_expires_at = None
        await self.session.commit()
        return _whiteboard_notification_to_dict(row)

    async def create_schedule_request(self, audit_run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        audit_run = await self._audit_run(audit_run_id)
        goal = str(body.get("goal") or "").strip()
        if not goal:
            raise ValueError("goal is required")
        related_card_ids = [str(item) for item in body.get("related_card_ids") or [] if str(item).strip()]
        low_value_reason = await self._low_value_only_schedule_reason(audit_run_id, related_card_ids)
        row = WhiteboardScheduleRequest(
            request_id=str(uuid.uuid4()),
            audit_run_id=audit_run_id,
            project_id=audit_run.project_id,
            requested_by_task_id=self._optional_str(body.get("requested_by_task_id") or body.get("task_id"), 128),
            requested_by_agent_run_id=self._optional_str(body.get("requested_by_agent_run_id") or body.get("agent_run_id"), 128),
            suggested_agent_name=self._optional_str(body.get("suggested_agent_name"), 128),
            goal=goal,
            reason=self._optional_str(body.get("reason"), 10000),
            related_card_ids=related_card_ids,
            status="rejected" if low_value_reason else "pending",
            decision={"reason": low_value_reason, "policy": "low_value_swarm_triage"} if low_value_reason else {},
        )
        self.session.add(row)
        await self.record_event(
            audit_run_id,
            entity_type="schedule-request",
            entity_id=row.request_id,
            event_type="rejected" if low_value_reason else "created",
            summary=(f"Low-value agent help rejected: {goal[:160]}" if low_value_reason else f"Agent help requested: {goal[:160]}"),
            payload={"schedule_request": _whiteboard_schedule_request_to_dict(row)},
            project_id=audit_run.project_id,
        )
        await self.session.commit()
        return _whiteboard_schedule_request_to_dict(row)

    async def decide_schedule_request(self, audit_run_id: str, request_id: str, body: dict[str, Any]) -> dict[str, Any]:
        audit_run = await self._audit_run(audit_run_id)
        row = await self.session.scalar(
            select(WhiteboardScheduleRequest).where(
                WhiteboardScheduleRequest.audit_run_id == audit_run_id,
                WhiteboardScheduleRequest.request_id == request_id,
            )
        )
        if not row:
            raise LookupError("whiteboard schedule request not found")
        status = self._safe_token(body.get("status") or body.get("decision") or "approved", "approved")
        if status not in {"approved", "rejected", "merged", "scheduled"}:
            raise ValueError("schedule request decision must be approved, rejected, merged, or scheduled")
        low_value_reason = await self._low_value_only_schedule_reason(audit_run_id, row.related_card_ids or [])
        if status in {"approved", "scheduled"} and low_value_reason:
            status = "rejected"
            body = {**body, "decision": {"reason": low_value_reason, "policy": "low_value_swarm_triage"}}
        row.status = status
        row.decision = dict(body.get("decision") or body)
        row.task_id = self._optional_str(body.get("task_id"), 128)
        if status in {"approved", "scheduled"} and not row.task_id:
            task = WhiteboardTask(
                task_id=str(uuid.uuid4()),
                audit_run_id=audit_run_id,
                project_id=audit_run.project_id,
                gap_card_id=(row.related_card_ids or [None])[0],
                card_id=(row.related_card_ids or [None])[0],
                agent_role="whiteboard-requested-agent",
                agent_name=str(body.get("agent_name") or row.suggested_agent_name or "opencode-source-sink-finder"),
                status="queued",
                parent_task_id=self._optional_str(body.get("parent_task_id") or row.requested_by_task_id, 128),
                root_task_id=self._optional_str(body.get("root_task_id") or row.requested_by_task_id, 128),
                task_group=self._optional_str(body.get("task_group"), 128),
                requested_by_agent_run_id=row.requested_by_agent_run_id,
                prompt=row.goal,
                result={"schedule_request_id": row.request_id, "reason": row.reason},
            )
            self.session.add(task)
            row.task_id = task.task_id
        await self.record_event(
            audit_run_id,
            entity_type="schedule-request",
            entity_id=row.request_id,
            event_type=status,
            summary=f"Schedule request {status}: {row.goal[:160]}",
            payload={"schedule_request": _whiteboard_schedule_request_to_dict(row)},
            project_id=audit_run.project_id,
        )
        await self.session.commit()
        return _whiteboard_schedule_request_to_dict(row)

    async def _low_value_only_schedule_reason(self, audit_run_id: str, related_card_ids: list[str]) -> str | None:
        if not related_card_ids:
            return "Schedule requests must reference at least one Whiteboard card with a main-agent deep_dive triage decision."
        cards = (
            await self.session.execute(
                select(WhiteboardCard).where(
                    WhiteboardCard.audit_run_id == audit_run_id,
                    WhiteboardCard.card_id.in_(related_card_ids),
                )
            )
        ).scalars().all()
        if not cards:
            return "Schedule requests must reference existing Whiteboard cards."
        card_ids = [card.card_id for card in cards]
        finding_ids = [str(card.finding_id) for card in cards if card.finding_id]
        decision_rows = (
            await self.session.execute(
                select(FindingTriageDecision).where(
                    FindingTriageDecision.audit_run_id == audit_run_id,
                    (
                        FindingTriageDecision.card_id.in_(card_ids)
                        if not finding_ids
                        else (
                            FindingTriageDecision.card_id.in_(card_ids)
                            | FindingTriageDecision.finding_id.in_(finding_ids)
                        )
                    ),
                )
            )
        ).scalars().all()
        if any(row.decision_status == "deep_dive" and row.deep_dive_allowed for row in decision_rows):
            return None
        decisions = [str(row.decision_status or "") for row in decision_rows]
        for card in cards:
            triage = (card.metadata_json or {}).get("swarm_triage")
            if isinstance(triage, dict):
                decisions.append(str(triage.get("decision") or ""))
        if not decisions:
            return "No main-agent deep_dive triage decision is recorded for the related cards; Swarm scheduling is blocked."
        if any(item in {"deep_dive", "chain_candidate"} for item in decisions):
            return None
        return "All related cards were triaged as low-value, evidence-only, appendix-only, or rejected; Swarm must not launch agents for standalone hygiene findings."

    async def agent_graph(self, audit_run_id: str) -> dict[str, Any]:
        graph = await self.graph(audit_run_id)
        tasks = graph["tasks"]
        nodes = [
            {
                "id": f"task:{task['task_id']}",
                "kind": "whiteboard-task",
                "label": task.get("agent_role") or task.get("agent_name"),
                "status": task.get("status"),
                "data": task,
            }
            for task in tasks
        ]
        task_ids = {task["task_id"] for task in tasks}
        edges: list[dict[str, Any]] = []
        for task in tasks:
            parent = task.get("parent_task_id")
            if parent and parent in task_ids:
                edges.append({"source": f"task:{parent}", "target": f"task:{task['task_id']}", "type": "parent"})
            card_id = task.get("card_id") or task.get("gap_card_id")
            if card_id:
                edges.append({"source": f"card:{card_id}", "target": f"task:{task['task_id']}", "type": "works-on"})
        return {"audit_run_id": audit_run_id, "project_id": graph["project_id"], "nodes": nodes, "edges": edges, "summary": {"task_count": len(tasks)}}

    async def record_event(
        self,
        audit_run_id: str,
        *,
        entity_type: str,
        entity_id: str,
        event_type: str,
        summary: str | None,
        payload: dict[str, Any],
        project_id: str | None = None,
    ) -> WhiteboardEvent:
        audit_run = None if project_id else await self._audit_run(audit_run_id)
        event = WhiteboardEvent(
            event_id=str(uuid.uuid4()),
            audit_run_id=audit_run_id,
            project_id=project_id or audit_run.project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            summary=summary,
            payload=payload,
        )
        self.session.add(event)
        await self.session.flush()
        await self._fanout_notifications(event)
        return event

    async def write_snapshot(self, audit_run_id: str) -> dict[str, Any]:
        graph = await self.graph(audit_run_id)
        return self.artifacts.put_json(self._snapshot_path(audit_run_id), graph)

    async def pending_gap_cards(self, audit_run_id: str, *, limit: int) -> list[WhiteboardCard]:
        rows = (
            await self.session.execute(
                select(WhiteboardCard)
                .where(WhiteboardCard.audit_run_id == audit_run_id)
                .where(WhiteboardCard.card_type == "gap")
                .where(WhiteboardCard.status.in_(["open", "needs_agent"]))
                .order_by(WhiteboardCard.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        return list(rows)

    async def task_attempt_count(self, audit_run_id: str, gap_card_id: str) -> int:
        rows = (
            await self.session.execute(
                select(WhiteboardTask).where(WhiteboardTask.audit_run_id == audit_run_id, WhiteboardTask.gap_card_id == gap_card_id)
            )
        ).scalars().all()
        return len(rows)

    async def create_task_for_gap(self, audit_run: AuditRun, gap: WhiteboardCard, *, round_index: int, attempt_index: int) -> WhiteboardTask:
        gap_kind = str((gap.metadata_json or {}).get("gap_kind") or gap.metadata_json.get("kind") if gap.metadata_json else "").strip().lower()
        agent_role, default_agent_name = WHITEBOARD_AGENT_BY_GAP_TYPE.get(gap_kind, ("source-sink-finder", "opencode-source-sink-finder"))
        config = audit_run.config or {}
        agent_name = str(config.get(f"{agent_role.replace('-', '_')}_agent_name") or default_agent_name)
        task = WhiteboardTask(
            task_id=str(uuid.uuid4()),
            audit_run_id=audit_run.audit_run_id,
            project_id=audit_run.project_id,
            gap_card_id=gap.card_id,
            card_id=gap.card_id,
            agent_role=agent_role,
            agent_name=agent_name,
            status="queued",
            round_index=round_index,
            attempt_index=attempt_index,
            task_group=str((gap.metadata_json or {}).get("source_trace_group") or (gap.metadata_json or {}).get("task_group") or "")[:128] or None,
            prompt=f"Resolve whiteboard gap `{gap.card_id}`: {gap.title}\n\n{gap.content or ''}",
            result={},
        )
        self.session.add(task)
        gap.status = "agent_queued"
        await self.record_event(
            audit_run.audit_run_id,
            entity_type="task",
            entity_id=task.task_id,
            event_type="created",
            summary=f"Whiteboard task queued: {gap.title}",
            payload={"task": _whiteboard_task_to_dict(task)},
            project_id=audit_run.project_id,
        )
        await self.session.commit()
        await self.write_snapshot(audit_run.audit_run_id)
        return task

    def _snapshot_path(self, audit_run_id: str) -> str:
        return f"whiteboards/{audit_run_id}/whiteboard.json"

    async def _audit_run(self, audit_run_id: str) -> AuditRun:
        row = await self.session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
        if not row:
            raise LookupError("audit run not found")
        return row

    async def _card(self, audit_run_id: str, card_id: str) -> WhiteboardCard:
        row = await self.session.scalar(select(WhiteboardCard).where(WhiteboardCard.audit_run_id == audit_run_id, WhiteboardCard.card_id == card_id))
        if not row:
            raise LookupError("whiteboard card not found")
        return row

    async def _edge(self, audit_run_id: str, edge_id: str) -> WhiteboardEdge:
        row = await self.session.scalar(select(WhiteboardEdge).where(WhiteboardEdge.audit_run_id == audit_run_id, WhiteboardEdge.edge_id == edge_id))
        if not row:
            raise LookupError("whiteboard edge not found")
        return row

    @staticmethod
    def _optional_str(value: Any, limit: int) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text[:limit] if text else None

    @staticmethod
    def _safe_token(value: Any, fallback: str) -> str:
        text = str(value or "").strip().lower().replace("_", "-")
        text = "".join(ch for ch in text if ch.isalnum() or ch == "-").strip("-")
        return text[:64] or fallback

    @staticmethod
    def _parse_event_time(value: Any) -> datetime | None:
        if not value:
            return datetime.now(timezone.utc)
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)

    @staticmethod
    def _validate_attachment_path(path: str) -> str:
        normalized = path.strip().replace("\\", "/")
        if not normalized or normalized.startswith("/") or "://" in normalized:
            raise ValueError("attachment path must be a relative workspace or artifact path")
        pure = PurePosixPath(normalized)
        if any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError("attachment path contains unsafe segments")
        allowed = ("findings/", "agent-runs/", "reports/", "whiteboards/", "mcp-runs/", "workspace/")
        if not normalized.startswith(allowed):
            raise ValueError(f"attachment path must start with one of {allowed}")
        return normalized

    @classmethod
    def _normalize_link_candidates(cls, value: Any) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in value or []:
            if isinstance(item, str):
                raw = {"title": item}
            elif isinstance(item, dict):
                raw = dict(item)
            else:
                continue
            status = str(raw.get("status") or "not_ready").strip().lower().replace("-", "_").replace(" ", "_")
            if status not in WHITEBOARD_LINK_STATUSES:
                status = "not_ready"
            agent_run_id = raw.get("agent_run_id") or raw.get("agent_id")
            card_ids = [str(value).strip() for value in raw.get("card_ids") or [] if str(value).strip()]
            normalized = {
                "title": cls._optional_str(raw.get("title"), 255),
                "card_ids": card_ids[:50],
                "status": status,
                "agent_run_id": cls._optional_str(agent_run_id, 128),
                "rationale": cls._optional_str(raw.get("rationale"), 2000),
                "metadata": dict(raw.get("metadata") or {}),
            }
            if normalized["title"] or normalized["card_ids"] or normalized["rationale"]:
                candidates.append(normalized)
        return candidates

    @staticmethod
    def _evidence_summary(cards: list[WhiteboardCard]) -> str:
        titles = [card.title for card in cards[:5]]
        return "Whiteboard chain: " + " -> ".join(titles) if titles else "Whiteboard chain evidence"

    @staticmethod
    def _card_has_candidate_status(card: WhiteboardCard, status: str) -> bool:
        normalized = status.strip().lower().replace("-", "_").replace(" ", "_")
        for group in (card.expected_predecessors or [], card.possible_successors or []):
            if isinstance(group, dict) and str(group.get("status") or "").lower() == normalized:
                return True
        return False

    async def _fanout_notifications(self, event: WhiteboardEvent) -> None:
        subscriptions = (
            await self.session.execute(
                select(WhiteboardSubscription)
                .where(WhiteboardSubscription.audit_run_id == event.audit_run_id)
                .where(WhiteboardSubscription.status == "active")
            )
        ).scalars().all()
        for subscription in subscriptions:
            if not self._subscription_matches(subscription, event):
                continue
            existing = await self.session.scalar(
                select(WhiteboardNotification).where(
                    WhiteboardNotification.event_id == event.event_id,
                    WhiteboardNotification.subscription_id == subscription.subscription_id,
                )
            )
            if existing:
                continue
            self.session.add(
                WhiteboardNotification(
                    notification_id=str(uuid.uuid4()),
                    audit_run_id=event.audit_run_id,
                    project_id=event.project_id,
                    event_id=event.event_id,
                    subscription_id=subscription.subscription_id,
                    subscriber_task_id=subscription.subscriber_task_id,
                    subscriber_agent_run_id=subscription.subscriber_agent_run_id,
                    status="pending",
                    summary=event.summary,
                    payload={"event": _whiteboard_event_to_dict(event)},
                )
            )
            subscription.cursor_event_id = event.event_id

    @staticmethod
    def _subscription_matches(subscription: WhiteboardSubscription, event: WhiteboardEvent) -> bool:
        filters = subscription.filter_json or {}
        card_ids = {str(item) for item in filters.get("card_ids") or [] if str(item).strip()}
        if card_ids and event.entity_id not in card_ids:
            payload_card_id = str((event.payload or {}).get("card_id") or "")
            if payload_card_id not in card_ids:
                return False
        entity_types = {str(item) for item in filters.get("entity_types") or [] if str(item).strip()}
        if entity_types and event.entity_type not in entity_types:
            return False
        event_types = {str(item) for item in filters.get("event_types") or [] if str(item).strip()}
        if event_types and event.event_type not in event_types:
            return False
        card_types = {str(item) for item in filters.get("card_types") or [] if str(item).strip()}
        if card_types:
            card = (event.payload or {}).get("card") if isinstance(event.payload, dict) else {}
            if not isinstance(card, dict) or str(card.get("card_type") or "") not in card_types:
                return False
        statuses = {str(item) for item in filters.get("statuses") or [] if str(item).strip()}
        if statuses:
            card = (event.payload or {}).get("card") if isinstance(event.payload, dict) else {}
            if not isinstance(card, dict) or str(card.get("status") or "") not in statuses:
                return False
        keywords = [str(item).lower() for item in filters.get("keywords") or [] if str(item).strip()]
        if keywords:
            haystack = f"{event.summary or ''} {event.entity_type} {event.event_type} {event.payload}".lower()
            if not any(keyword in haystack for keyword in keywords):
                return False
        topics = [str(item).lower() for item in filters.get("topics") or [] if str(item).strip()]
        if topics:
            haystack = f"{event.summary or ''} {event.payload}".lower()
            if not any(topic in haystack for topic in topics):
                return False
        capabilities = [str(item).lower() for item in filters.get("capabilities") or [] if str(item).strip()]
        if capabilities:
            card = (event.payload or {}).get("card") if isinstance(event.payload, dict) else {}
            metadata = card.get("metadata") if isinstance(card, dict) and isinstance(card.get("metadata"), dict) else {}
            required = [str(item).lower() for item in metadata.get("required_capabilities") or metadata.get("capabilities") or []]
            if required and not set(capabilities).intersection(required):
                return False
        dependency_card_ids = {str(item) for item in filters.get("dependency_card_ids") or [] if str(item).strip()}
        if dependency_card_ids:
            payload = event.payload if isinstance(event.payload, dict) else {}
            related_ids = {str(payload.get("card_id") or ""), str(event.entity_id or "")}
            edge = payload.get("edge") if isinstance(payload.get("edge"), dict) else {}
            related_ids.update(str(edge.get(key) or "") for key in ("source_card_id", "target_card_id"))
            if not dependency_card_ids.intersection(related_ids):
                return False
        return True

from __future__ import annotations

from fastapi import APIRouter
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dieaudit_common.domain.models import AgentRun, AgentTranscriptEvent
from dieaudit_common.persistence.base import SessionLocal
from app.application.execution_graph import audit_run_execution_graph

router = APIRouter(prefix="/api/bff/audit-runs", tags=["agent-messages"])


@router.get("/{audit_run_id}/agent-runs/{agent_run_id}/messages")
async def agent_run_messages(audit_run_id: str, agent_run_id: str) -> list[dict]:
    async with SessionLocal() as session:
      return await _messages(session, audit_run_id, agent_run_id)


@router.get("/{audit_run_id}/flow")
async def audit_run_flow(audit_run_id: str) -> dict:
    async with SessionLocal() as session:
        result = await audit_run_execution_graph(session, audit_run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="audit run not found")
        return result


@router.get("/{audit_run_id}/whiteboard/flow")
async def whiteboard_flow(audit_run_id: str) -> dict:
    return {"audit_run_id": audit_run_id, "nodes": [], "edges": [], "summary": {"status": "use-whiteboard-bundle"}}


async def _messages(session: AsyncSession, audit_run_id: str, agent_run_id: str) -> list[dict]:
    rows = (
        await session.execute(
            select(AgentTranscriptEvent)
            .where(AgentTranscriptEvent.audit_run_id == audit_run_id, AgentTranscriptEvent.agent_run_id == agent_run_id)
            .order_by(AgentTranscriptEvent.seq.asc(), AgentTranscriptEvent.id.asc())
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "agent_run_id": row.agent_run_id,
            "audit_run_id": row.audit_run_id,
            "runtime_id": row.runtime_id,
            "seq": row.seq,
            "event_type": row.event_type,
            "session_id": row.session_id,
            "payload": row.payload or {},
            "content_text": row.content_text,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]

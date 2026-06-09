from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.domain.models import Finding


def finding_identity(
    *,
    title: Any,
    source: Any,
    file_path: Any,
    line_start: Any,
    rule_id: Any = None,
) -> dict[str, Any]:
    return {
        "title": str(title or "Finding")[:255],
        "source": str(source or "unknown"),
        "file_path": str(file_path) if file_path else None,
        "line_start": optional_int(line_start),
        "rule_id": str(rule_id) if rule_id else None,
    }


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def find_existing_finding(
    session,
    *,
    audit_run_id: str,
    identity: dict[str, Any],
) -> Finding | None:
    conditions = [
        Finding.audit_run_id == audit_run_id,
        Finding.title == identity["title"],
        Finding.source == identity["source"],
        Finding.file_path == identity["file_path"],
        Finding.line_start == identity["line_start"],
    ]
    if identity.get("rule_id"):
        conditions.append(Finding.rule_id == identity["rule_id"])
    else:
        conditions.append(Finding.rule_id.is_(None))
    return await session.scalar(select(Finding).where(*conditions).limit(1))

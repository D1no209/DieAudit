from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from sqlalchemy import select

from dieaudit_common.domain.models import WorkerHeartbeat
from dieaudit_common.persistence.base import SessionLocal


async def _check() -> None:
    ttl_seconds = max(1, int(float(os.getenv("PIPELINE_WORKER_HEARTBEAT_TTL_SECONDS", "30"))))
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        row = await session.scalar(
            select(WorkerHeartbeat)
            .where(WorkerHeartbeat.service_name == "workflow-worker")
            .order_by(WorkerHeartbeat.last_seen_at.desc())
            .limit(1)
        )
    if row is None:
        raise SystemExit("no workflow-worker heartbeat recorded")
    last_seen = row.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    age_seconds = (now - last_seen).total_seconds()
    if age_seconds > ttl_seconds:
        raise SystemExit(f"workflow-worker heartbeat is stale: {age_seconds:.1f}s > {ttl_seconds}s")
    if row.status == "stopped":
        raise SystemExit("latest workflow-worker heartbeat is stopped")


def main() -> None:
    asyncio.run(_check())


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dieaudit_common.domain.models import ApiKey
from dieaudit_common.persistence.repositories import new_id


def generate_api_key() -> str:
    return f"dieaudit_{secrets.token_urlsafe(32)}"


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def create_api_key(session: AsyncSession, *, name: str, scopes: list[str]) -> dict:
    api_key = generate_api_key()
    row = ApiKey(
        key_id=new_id("key"),
        name=name,
        key_hash=hash_api_key(api_key),
        scopes=scopes or ["admin"],
        status="active",
        metadata_json={"schema_version": 1},
    )
    session.add(row)
    return {"api_key": api_key, "record": api_key_to_dict(row)}


async def authenticate(session: AsyncSession, supplied: str | None) -> dict | None:
    if not supplied:
        return None
    row = await session.scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(supplied), ApiKey.status == "active"))
    if row is None:
        return None
    row.last_used_at = datetime.now(timezone.utc)
    return {"key_id": row.key_id, "name": row.name, "scopes": row.scopes, "source": "persisted"}


def api_key_to_dict(row: ApiKey) -> dict:
    return {
        "key_id": row.key_id,
        "name": row.name,
        "scopes": row.scopes,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
    }

from contextvars import ContextVar, Token
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.domain.models import ApiKeyRecord
from app.repositories import SessionLocal
from app.settings import Settings


API_KEY_PREFIX = "dak_"
BOOTSTRAP_KEY_ID = "env-bootstrap"
_current_api_key: ContextVar[str | None] = ContextVar("dieaudit_current_api_key", default=None)


def generate_api_key() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def set_current_api_key(value: str | None) -> Token[str | None]:
    return _current_api_key.set(value)


def reset_current_api_key(token: Token[str | None]) -> None:
    _current_api_key.reset(token)


def get_current_api_key() -> str | None:
    return _current_api_key.get()


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def has_scope(principal: dict[str, Any] | None, scope: str) -> bool:
    scopes = set((principal or {}).get("scopes") or [])
    return "*" in scopes or scope in scopes


def can_access_scope(principal: dict[str, Any] | None, required_scope: str | None, method: str) -> bool:
    if not required_scope:
        return True
    if has_scope(principal, "admin"):
        return True
    if has_scope(principal, required_scope):
        return True
    if method.upper() == "GET" and required_scope != "admin" and has_scope(principal, "read"):
        return True
    return False


def required_scope_for_path(method: str, path: str) -> str | None:
    normalized_method = method.upper()
    if normalized_method in {"OPTIONS", "HEAD"}:
        return None
    if path == "/auth/me":
        return None
    if path.startswith("/auth/api-keys"):
        return "admin"
    if path.startswith("/platform"):
        return "admin"
    if path.startswith("/runtime/templates") or path.startswith("/runtime/policy"):
        return "admin"
    if path.startswith("/runtime"):
        return "runtime"
    if path == "/knowledge/search":
        return "read"
    if path.startswith("/knowledge"):
        return "audit"
    if path.startswith("/projects") or path.startswith("/audit-runs") or path.startswith("/findings") or path.startswith("/reports"):
        return "audit"
    if path == "/metrics":
        return "admin"
    return None


def bootstrap_principal(settings: Settings) -> dict[str, Any]:
    return {
        "key_id": BOOTSTRAP_KEY_ID,
        "name": "Environment bootstrap key",
        "source": "env",
        "scopes": ["*"],
    }


async def auth_is_enabled(settings: Settings) -> bool:
    if settings.dieaudit_api_key:
        return True
    try:
        async with SessionLocal() as session:
            key_id = await session.scalar(select(ApiKeyRecord.key_id).where(ApiKeyRecord.status == "active").limit(1))
            return bool(key_id)
    except Exception:
        return False


async def authenticate_api_key(settings: Settings, supplied: str | None) -> dict[str, Any] | None:
    if not supplied:
        return None
    if settings.dieaudit_api_key and secrets.compare_digest(supplied, settings.dieaudit_api_key):
        return bootstrap_principal(settings)
    digest = hash_api_key(supplied)
    async with SessionLocal() as session:
        row = await session.scalar(
            select(ApiKeyRecord).where(
                ApiKeyRecord.key_hash == digest,
                ApiKeyRecord.status == "active",
            )
        )
        if not row:
            return None
        row.last_used_at = datetime.now(timezone.utc)
        await session.commit()
        return api_key_principal(row)


def api_key_principal(row: ApiKeyRecord) -> dict[str, Any]:
    return {
        "key_id": row.key_id,
        "name": row.name,
        "source": "database",
        "scopes": row.scopes or [],
    }


def api_key_record_to_dict(row: ApiKeyRecord) -> dict[str, Any]:
    return {
        "key_id": row.key_id,
        "name": row.name,
        "scopes": row.scopes or [],
        "status": row.status,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "deactivated_at": row.deactivated_at.isoformat() if row.deactivated_at else None,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }

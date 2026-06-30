from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings import get_settings
from dieaudit_common.domain.models import ApiKey
from dieaudit_common.persistence.base import get_session
from dieaudit_common.security.api_keys import authenticate

router = APIRouter(prefix="/api/bff/session", tags=["session"])


@router.get("")
async def session(request: Request, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    settings = get_settings()
    principal = await _authenticate(request, db)
    return {
        "authenticated": bool(principal),
        "api_key_header": settings.api_key_header,
        "principal": principal,
        "service": settings.service_name,
    }


@router.get("/status")
async def status(db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    settings = get_settings()
    persisted_key_exists = await db.scalar(select(ApiKey.key_id).where(ApiKey.status == "active").limit(1))
    return {
        "enabled": bool(_password_login_enabled(settings) or settings.dieaudit_api_key.strip() or persisted_key_exists),
        "bootstrap_key_enabled": bool(settings.dieaudit_api_key.strip()),
        "password_login_enabled": _password_login_enabled(settings),
        "api_key_header": settings.api_key_header,
        "public_metrics": False,
        "service": settings.service_name,
    }


@router.post("/login")
async def login(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    principal = _authenticate_admin_password(settings, username, password)
    if not principal:
        raise HTTPException(status_code=401, detail="登录凭证无效")
    access_token = settings.dieaudit_api_key.strip()
    if not access_token:
        raise HTTPException(status_code=503, detail="管理员登录需要配置 DIEAUDIT_API_KEY 作为内部访问令牌")
    return {
        "authenticated": True,
        "access_token": access_token,
        "api_key_header": settings.api_key_header,
        "principal": principal,
        "service": settings.service_name,
    }


async def _authenticate(request: Request, db: AsyncSession) -> dict[str, Any] | None:
    settings = get_settings()
    supplied = _supplied_api_key(request, settings)
    if not supplied:
        return None
    bootstrap_key = settings.dieaudit_api_key.strip()
    if bootstrap_key and secrets.compare_digest(supplied, bootstrap_key):
        return {"key_id": "bootstrap", "name": "Bootstrap administrator", "scopes": ["admin"], "source": "bootstrap"}
    principal = await authenticate(db, supplied)
    if principal:
        await db.commit()
    return principal


def _supplied_api_key(request: Request, settings: Any) -> str | None:
    supplied = request.headers.get(settings.api_key_header) or _bearer_token(request.headers.get("Authorization"))
    return supplied.strip() if supplied and supplied.strip() else None


def _authenticate_admin_password(settings: Any, username: str, password: str) -> dict[str, Any] | None:
    if not _password_login_enabled(settings):
        return None
    if not secrets.compare_digest(username, settings.dieaudit_admin_username):
        return None
    if not secrets.compare_digest(password, settings.dieaudit_admin_password):
        return None
    return {"key_id": "admin", "name": "Administrator", "scopes": ["admin"], "source": "password"}


def _password_login_enabled(settings: Any) -> bool:
    return bool(settings.dieaudit_admin_username.strip() and settings.dieaudit_admin_password.strip())


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()

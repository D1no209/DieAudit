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

router = APIRouter(tags=["session"])


@router.get("/auth/status")
async def auth_status(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    settings = get_settings()
    persisted_key_exists = await session.scalar(select(ApiKey.key_id).where(ApiKey.status == "active").limit(1))
    return {
        "enabled": bool(_password_login_enabled(settings) or settings.dieaudit_api_key or persisted_key_exists),
        "bootstrap_key_enabled": bool(settings.dieaudit_api_key),
        "api_key_header": settings.api_key_header,
        "public_metrics": False,
        "service": settings.service_name,
    }


@router.get("/bff/session")
@router.get("/api/bff/session")
async def session(request: Request, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    settings = get_settings()
    principal = await _authenticate(request, session)
    return {
        "authenticated": bool(principal),
        "api_key_header": settings.api_key_header,
        "principal": principal,
        "service": settings.service_name,
    }


@router.post("/bff/session/login")
@router.post("/api/bff/session/login")
async def login(payload: dict[str, Any], session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    settings = get_settings()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    principal = _authenticate_admin_password(settings, username, password)
    if not principal:
        raise HTTPException(status_code=401, detail="登录凭证无效")
    if not settings.dieaudit_api_key:
        raise HTTPException(status_code=503, detail="管理员登录需要配置 DIEAUDIT_API_KEY 作为内部访问令牌")
    return {
        "authenticated": True,
        "access_token": settings.dieaudit_api_key,
        "api_key_header": settings.api_key_header,
        "principal": principal,
        "service": settings.service_name,
    }


async def _authenticate(request: Request, session: AsyncSession) -> dict[str, Any] | None:
    settings = get_settings()
    supplied = request.headers.get(settings.api_key_header) or _bearer_token(request.headers.get("Authorization"))
    return await _authenticate_supplied(settings, session, supplied)


async def _authenticate_supplied(settings: Any, session: AsyncSession, supplied: str | None) -> dict[str, Any] | None:
    if not supplied:
        return None
    if settings.dieaudit_api_key and secrets.compare_digest(supplied, settings.dieaudit_api_key):
        return {"key_id": "bootstrap", "name": "Bootstrap administrator", "scopes": ["admin"], "source": "bootstrap"}
    principal = await authenticate(session, supplied)
    if principal:
        await session.commit()
    return principal


def _authenticate_admin_password(settings: Any, username: str, password: str) -> dict[str, Any] | None:
    if not _password_login_enabled(settings):
        return None
    if not secrets.compare_digest(username, settings.dieaudit_admin_username):
        return None
    if not secrets.compare_digest(password, settings.dieaudit_admin_password):
        return None
    return {"key_id": "admin", "name": "Administrator", "scopes": ["admin"], "source": "password"}


def _password_login_enabled(settings: Any) -> bool:
    return bool(settings.dieaudit_admin_username and settings.dieaudit_admin_password)


def _bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()

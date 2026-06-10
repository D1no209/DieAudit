from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.cli.create_api_key import expand_scopes, parse_metadata
from app.services.auth import (
    _api_key_is_expired,
    api_key_principal,
    authenticate_api_key,
    can_access_scope,
    hash_api_key,
    normalize_scopes,
    required_scope_for_path,
)
import app.services.auth as auth_module


def test_expand_scopes_accepts_repeated_and_comma_separated_values() -> None:
    assert expand_scopes(["admin,runtime", "audit"]) == ["admin", "runtime", "audit"]


def test_expand_scopes_defaults_to_admin_for_cli_bootstrap() -> None:
    assert expand_scopes([]) == ["admin"]


def test_parse_metadata_requires_json_object() -> None:
    assert parse_metadata('{"source":"ops"}') == {"source": "ops"}
    with pytest.raises(SystemExit):
        parse_metadata("[]")


def test_normalize_scopes_uses_caller_default_for_empty_values() -> None:
    assert normalize_scopes([], default_scope="read") == ["read"]
    assert normalize_scopes([" runtime ", "audit", "audit"], default_scope="read") == ["audit", "runtime"]


def test_artifact_routes_require_audit_scope_with_read_allowed_for_get() -> None:
    assert required_scope_for_path("GET", "/artifacts/download") == "audit"
    assert can_access_scope({"scopes": ["read"]}, "audit", "GET")
    assert not can_access_scope({"scopes": ["runtime"]}, "audit", "GET")


def test_api_key_principal_includes_metadata() -> None:
    class Row:
        key_id = "key-1"
        name = "Project key"
        scopes = ["read"]
        metadata_json = {"project_ids": ["project-1"]}

    principal = api_key_principal(Row())

    assert principal["metadata"] == {"project_ids": ["project-1"]}


def test_api_key_expiration_metadata_is_enforced() -> None:
    class Row:
        metadata_json = {"expires_at": "2026-06-10T00:00:00+00:00"}

    assert _api_key_is_expired(Row(), now=datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc))
    assert _api_key_is_expired(Row(), now=datetime(2026, 6, 10, 0, 1, tzinfo=timezone.utc))
    assert not _api_key_is_expired(Row(), now=datetime(2026, 6, 9, 23, 59, tzinfo=timezone.utc))


def test_api_key_expiration_ignores_missing_or_invalid_metadata() -> None:
    class Missing:
        metadata_json = {}

    class Invalid:
        metadata_json = {"expires_at": "not-a-date"}

    now = datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc)
    assert not _api_key_is_expired(Missing(), now=now)
    assert not _api_key_is_expired(Invalid(), now=now)


def test_authenticate_api_key_deactivates_expired_persisted_key(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_run_authenticate_api_key_deactivates_expired_persisted_key(monkeypatch))


async def _run_authenticate_api_key_deactivates_expired_persisted_key(monkeypatch: pytest.MonkeyPatch) -> None:
    row = SimpleNamespace(
        key_id="key-1",
        name="expired",
        key_hash=hash_api_key("dak_expired"),
        scopes=["read"],
        status="active",
        last_used_at=None,
        deactivated_at=None,
        metadata_json={"expires_at": "2000-01-01T00:00:00+00:00"},
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def scalar(self, _statement):
            return row

        async def commit(self):
            self.committed = True

    monkeypatch.setattr(auth_module, "SessionLocal", lambda: FakeSession())

    principal = await authenticate_api_key(SimpleNamespace(dieaudit_api_key=""), "dak_expired")

    assert principal is None
    assert row.status == "inactive"
    assert row.deactivated_at is not None
    assert row.last_used_at is None

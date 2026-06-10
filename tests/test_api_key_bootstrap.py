from __future__ import annotations

import pytest

from app.cli.create_api_key import expand_scopes, parse_metadata
from app.services.auth import can_access_scope, normalize_scopes, required_scope_for_path


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

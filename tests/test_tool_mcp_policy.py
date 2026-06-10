from __future__ import annotations

import pytest
from httpx import Headers

import tool_mcp


def test_http_target_blocks_host_gateway() -> None:
    with pytest.raises(ValueError, match="blocked"):
        tool_mcp._validate_http_target("http://host.docker.internal:8080/health")


def test_http_target_requires_absolute_http_url() -> None:
    with pytest.raises(ValueError, match="absolute"):
        tool_mcp._validate_http_target("/relative/path")


def test_http_target_honors_allowed_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool_mcp, "HTTP_TEST_ALLOWED_HOSTS", {"target"})

    assert tool_mcp._validate_http_target("http://target:8080").hostname == "target"
    with pytest.raises(ValueError, match="not allowed"):
        tool_mcp._validate_http_target("http://other:8080")


def test_response_headers_strip_credentials() -> None:
    headers = Headers(
        {
            "content-type": "text/plain",
            "set-cookie": "session=secret",
            "authorization": "Bearer secret",
        }
    )

    safe = tool_mcp._safe_response_headers(headers)

    assert safe == {"content-type": "text/plain"}


def test_tool_capabilities_reports_requested_binaries() -> None:
    result = tool_mcp.tool_capabilities(["python", "definitely-not-a-dieaudit-tool"])

    assert result["binaries"]["python"]["available"] is True
    assert result["binaries"]["definitely-not-a-dieaudit-tool"]["available"] is False
    assert result["ok"] is False

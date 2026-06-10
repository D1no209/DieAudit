from __future__ import annotations

import pytest

from app.services.http_guards import FixedWindowRateLimiter, RequestBodyTooLarge, enforce_content_length_limit, parse_content_length


def test_parse_content_length_ignores_invalid_values() -> None:
    assert parse_content_length(None) is None
    assert parse_content_length("bad") is None
    assert parse_content_length("-1") is None
    assert parse_content_length("42") == 42


def test_content_length_limit_rejects_oversized_request() -> None:
    with pytest.raises(RequestBodyTooLarge):
        enforce_content_length_limit("101", max_bytes=100)


def test_fixed_window_rate_limiter_blocks_after_limit_and_resets() -> None:
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=10)

    assert limiter.check("key", now=100.0).allowed is True
    assert limiter.check("key", now=101.0).allowed is True
    blocked = limiter.check("key", now=102.0)
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 8

    reset = limiter.check("key", now=111.0)
    assert reset.allowed is True
    assert reset.remaining == 1


def test_fixed_window_rate_limiter_can_be_disabled() -> None:
    limiter = FixedWindowRateLimiter(limit=0, window_seconds=60)

    assert limiter.check("key").allowed is True

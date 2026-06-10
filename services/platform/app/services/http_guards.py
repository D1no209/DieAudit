from __future__ import annotations

from dataclasses import dataclass
import time


class RequestBodyTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class FixedWindowRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self.limit = max(0, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self._windows: dict[str, tuple[float, int]] = {}

    def check(self, key: str, *, now: float | None = None) -> RateLimitDecision:
        if self.limit <= 0:
            return RateLimitDecision(allowed=True, limit=0, remaining=0, retry_after_seconds=0)
        current = time.monotonic() if now is None else now
        window_start, count = self._windows.get(key, (current, 0))
        if current - window_start >= self.window_seconds:
            window_start = current
            count = 0
        count += 1
        self._windows[key] = (window_start, count)
        remaining = max(0, self.limit - count)
        retry_after = max(1, int(self.window_seconds - (current - window_start)))
        return RateLimitDecision(
            allowed=count <= self.limit,
            limit=self.limit,
            remaining=remaining,
            retry_after_seconds=0 if count <= self.limit else retry_after,
        )

    def prune(self, *, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        expired = [
            key
            for key, (window_start, _) in self._windows.items()
            if current - window_start >= self.window_seconds * 2
        ]
        for key in expired:
            self._windows.pop(key, None)


def parse_content_length(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def enforce_content_length_limit(value: str | None, *, max_bytes: int) -> int | None:
    content_length = parse_content_length(value)
    if content_length is not None and max_bytes > 0 and content_length > max_bytes:
        raise RequestBodyTooLarge(f"request body exceeds {max_bytes} bytes")
    return content_length

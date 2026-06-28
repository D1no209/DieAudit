from __future__ import annotations

from typing import Any

import httpx


class InternalServiceClient:
    def __init__(self, base_url: str, api_key_header: str, api_key: str | None = None) -> None:
        self.base_url = base_url
        self.api_key_header = api_key_header
        self.api_key = api_key

    async def request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> Any:
        headers = {}
        if self.api_key:
            headers[self.api_key_header] = self.api_key
        async with httpx.AsyncClient(base_url=self.base_url, timeout=120) as client:
            response = await client.request(method, path, json=json, headers=headers)
        response.raise_for_status()
        if "application/json" in response.headers.get("content-type", ""):
            return response.json()
        return response.text

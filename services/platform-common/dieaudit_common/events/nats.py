from __future__ import annotations

import json
from typing import Any

import nats

from dieaudit_common.domain.events import DomainEvent
from dieaudit_common.settings import CommonSettings


class EventPublisher:
    def __init__(self, settings: CommonSettings) -> None:
        self.settings = settings
        self._client: Any = None

    async def connect(self) -> None:
        if self._client is None:
            self._client = await nats.connect(self.settings.nats_url)

    async def publish(self, event: DomainEvent) -> None:
        await self.connect()
        await self._client.publish(event.subject, json.dumps(event.to_payload()).encode("utf-8"))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


class NullEventPublisher:
    async def publish(self, event: DomainEvent) -> None:
        return None

    async def close(self) -> None:
        return None

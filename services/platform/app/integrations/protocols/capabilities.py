from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ProtocolCapability:
    name: str
    available: bool
    import_path: str
    exported_symbols: list[str]
    error: str | None = None


def protocol_capabilities() -> dict[str, ProtocolCapability]:
    return {
        "agent_client_protocol": _capability(
            "agent_client_protocol",
            "acp",
            [
                "connect_to_agent",
                "spawn_agent_process",
                "Client",
                "Agent",
                "InitializeRequest",
                "PromptRequest",
                "NewSessionRequest",
            ],
        ),
        "a2a": _capability(
            "a2a",
            "a2a.client",
            ["Client", "ClientFactory", "ClientConfig", "A2ACardResolver", "create_client"],
        ),
    }


def serialize_capabilities() -> dict[str, Any]:
    return {name: capability.__dict__ for name, capability in protocol_capabilities().items()}


def classify_agent_protocol(template: dict[str, Any]) -> dict[str, Any]:
    protocol = template.get("protocol", {})
    if not protocol:
        acp_endpoint = template.get("acp_endpoint", {})
        protocol = {
            "kind": "legacy-http",
            "transport": acp_endpoint.get("transport", "http"),
            "port": acp_endpoint.get("port"),
        }
    kind = protocol.get("kind", "legacy-http")
    return {
        "agent": template.get("name"),
        "kind": kind,
        "transport": protocol.get("transport"),
        "stdio_command": protocol.get("stdio_command"),
        "a2a_card_url": protocol.get("agent_card_url"),
        "ready_for_agent_client_protocol": kind == "agent-client-protocol" and bool(protocol.get("stdio_command")),
        "ready_for_a2a": kind == "a2a" and bool(protocol.get("agent_card_url") or protocol.get("base_url")),
    }


async def fetch_a2a_agent_card(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url)
    response.raise_for_status()
    return response.json()


def _capability(name: str, import_path: str, symbols: list[str]) -> ProtocolCapability:
    try:
        module = importlib.import_module(import_path)
        exported = [symbol for symbol in symbols if hasattr(module, symbol)]
        return ProtocolCapability(name=name, available=True, import_path=import_path, exported_symbols=exported)
    except Exception as exc:
        return ProtocolCapability(
            name=name,
            available=False,
            import_path=import_path,
            exported_symbols=[],
            error=repr(exc),
        )

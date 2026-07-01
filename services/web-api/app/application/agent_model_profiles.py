from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dieaudit_common.domain.models import AgentModelProfile


KIMI_MODEL_PROVIDER_TYPES = ("openai", "openai_responses", "anthropic")
KIMI_MODEL_PROVIDER_TYPE_OPTIONS = (
    {
        "value": "openai",
        "label": "OpenAI Chat Completions",
        "description": "OpenAI-compatible /chat/completions wire type.",
    },
    {
        "value": "openai_responses",
        "label": "OpenAI Responses",
        "description": "OpenAI Responses API wire type.",
    },
    {
        "value": "anthropic",
        "label": "Anthropic",
        "description": "Anthropic Messages wire type.",
    },
)

AGENT_MODEL_ROLES = (
    "orchestrator",
    "code-auditor",
    "source-sink-finder",
    "validator",
    "judger",
    "poc-writer",
    "poc-verifier",
)

DEFAULT_PROFILE: dict[str, Any] = {
    "runtime_id": "kimi-code",
    "provider_type": "openai",
    "base_url": "",
    "model_name": "default",
    "api_key": "",
    "temperature": 0.1,
    "max_output_tokens": 8192,
    "context_window": 128000,
}


class AgentModelProfileApplication:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_config(self, *, include_secrets: bool = False) -> dict[str, Any]:
        rows = await self._rows_by_role()
        config = {
            "provider_type_options": list(KIMI_MODEL_PROVIDER_TYPE_OPTIONS),
            "roles": {role: self._row_or_default(role, rows.get(role)) for role in AGENT_MODEL_ROLES},
        }
        return config if include_secrets else public_agent_model_config(config)

    async def save_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self._rows_by_role()
        incoming_roles = payload.get("roles") if isinstance(payload.get("roles"), dict) else payload
        for role in AGENT_MODEL_ROLES:
            incoming = incoming_roles.get(role, {}) if isinstance(incoming_roles, dict) else {}
            existing = rows.get(role)
            if existing is None:
                existing = AgentModelProfile(role=role, metadata_json={"schema_version": 1})
                self.session.add(existing)
            merged = self._merge_profile(existing, incoming)
            existing.runtime_id = merged["runtime_id"]
            existing.provider_type = merged["provider_type"]
            existing.base_url = merged["base_url"] or None
            existing.model_name = merged["model_name"]
            existing.api_key = merged["api_key"] or None
            existing.temperature = merged["temperature"]
            existing.max_output_tokens = merged["max_output_tokens"]
            existing.context_window = merged["context_window"]
            existing.metadata_json = {**(existing.metadata_json or {}), "schema_version": 1}
        await self.session.flush()
        return await self.get_config()

    async def model_overrides(self) -> dict[str, Any]:
        config = await self.get_config(include_secrets=True)
        overrides: dict[str, Any] = {}
        for role, item in (config.get("roles") or {}).items():
            model_name = str(item.get("model_name") or "").strip()
            if not model_name:
                continue
            override = {
                "runtime_id": item.get("runtime_id") or DEFAULT_PROFILE["runtime_id"],
                "provider": item.get("provider_type") or DEFAULT_PROFILE["provider_type"],
                "model": model_name,
                "temperature": item.get("temperature"),
                "max_output_tokens": item.get("max_output_tokens"),
                "context_window": item.get("context_window"),
            }
            if item.get("base_url"):
                override["base_url"] = item["base_url"]
            if item.get("api_key"):
                override["api_key"] = item["api_key"]
            overrides[role] = override
        return overrides

    async def merge_model_overrides(self, config: dict[str, Any]) -> dict[str, Any]:
        merged = dict(config)
        defaults = await self.model_overrides()
        explicit = merged.get("model_overrides") if isinstance(merged.get("model_overrides"), dict) else {}
        merged["model_overrides"] = {**defaults, **explicit}
        return merged

    async def _rows_by_role(self) -> dict[str, AgentModelProfile]:
        rows = await self.session.execute(select(AgentModelProfile))
        return {row.role: row for row in rows.scalars()}

    def _row_or_default(self, role: str, row: AgentModelProfile | None) -> dict[str, Any]:
        if row is None:
            return {"role": role, **DEFAULT_PROFILE}
        return {
            "role": role,
            "runtime_id": row.runtime_id or DEFAULT_PROFILE["runtime_id"],
            "provider_type": row.provider_type or DEFAULT_PROFILE["provider_type"],
            "base_url": row.base_url or "",
            "model_name": row.model_name or DEFAULT_PROFILE["model_name"],
            "api_key": row.api_key or "",
            "temperature": row.temperature if row.temperature is not None else DEFAULT_PROFILE["temperature"],
            "max_output_tokens": row.max_output_tokens if row.max_output_tokens is not None else DEFAULT_PROFILE["max_output_tokens"],
            "context_window": row.context_window if row.context_window is not None else DEFAULT_PROFILE["context_window"],
        }

    def _merge_profile(self, existing: AgentModelProfile, incoming: dict[str, Any]) -> dict[str, Any]:
        current = self._row_or_default(existing.role, existing)
        api_key = str(incoming.get("api_key") or "")
        if not api_key:
            api_key = str(current.get("api_key") or "")
        return {
            "runtime_id": str(incoming.get("runtime_id") or current["runtime_id"]),
            "provider_type": normalize_provider_type(incoming.get("provider_type") or current["provider_type"]),
            "base_url": str(incoming.get("base_url") or current["base_url"] or ""),
            "model_name": str(incoming.get("model_name") or current["model_name"]),
            "api_key": api_key,
            "temperature": _number(incoming.get("temperature", current["temperature"]), DEFAULT_PROFILE["temperature"]),
            "max_output_tokens": _integer(incoming.get("max_output_tokens", current["max_output_tokens"]), DEFAULT_PROFILE["max_output_tokens"]),
            "context_window": _integer(incoming.get("context_window", current["context_window"]), DEFAULT_PROFILE["context_window"]),
        }


def normalize_provider_type(value: Any) -> str:
    provider_type = str(value or DEFAULT_PROFILE["provider_type"]).strip().lower().replace("-", "_")
    if provider_type not in KIMI_MODEL_PROVIDER_TYPES:
        allowed = ", ".join(KIMI_MODEL_PROVIDER_TYPES)
        raise ValueError(f"unsupported agent model provider type: {provider_type!r}; expected one of {allowed}")
    return provider_type


def public_agent_model_config(config: dict[str, Any]) -> dict[str, Any]:
    roles = {}
    for role, item in (config.get("roles") or {}).items():
        api_key = str((item or {}).get("api_key") or "")
        roles[role] = {key: value for key, value in (item or {}).items() if key != "api_key"}
        roles[role]["api_key_set"] = bool(api_key)
        roles[role]["api_key_preview"] = _secret_preview(api_key)
    return {"provider_type_options": config.get("provider_type_options") or [], "roles": roles}


def _secret_preview(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def _number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _integer(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

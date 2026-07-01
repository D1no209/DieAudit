from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from app.domain.models import RuntimePackage
from app.repositories import SessionLocal
from app.settings import Settings


class AgentRuntimePackageBuilder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def build(
        self,
        *,
        audit_run_id: str,
        project_id: str,
        agent_run_id: str,
        template: dict[str, Any],
        mcp_servers: dict[str, dict[str, Any]],
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        package_dir = self._package_dir(audit_run_id, agent_run_id)
        if package_dir.exists():
            shutil.rmtree(package_dir)
        (package_dir / "instructions").mkdir(parents=True, exist_ok=True)

        instruction_name = template.get("instruction") or f"{template.get('env', {}).get('AGENT_ROLE', template['name'])}.md"
        instruction_source = self.settings.config_root / "agent-instructions" / instruction_name
        instruction_target = package_dir / "instructions" / instruction_name
        if instruction_source.exists():
            shutil.copyfile(instruction_source, instruction_target)
        else:
            instruction_target.write_text(f"# {template['name']}\n\nFollow the audit task instructions.\n", encoding="utf-8")

        mcp_config = self._mcp_config(mcp_servers)
        runtime_config = self._runtime_config(template, mcp_config, instruction_target)
        self._write_json(package_dir / "agent-runtime.json", runtime_config)
        model_alias = self.model_alias_for_template(template, input_payload)
        kimi_config = self.kimi_config_toml(template, input_payload)
        if kimi_config:
            (package_dir / "config.toml").write_text(kimi_config, encoding="utf-8")
        self._write_json(package_dir / "mcp_servers.json", mcp_servers)
        self._write_json(
            package_dir / "input.json",
            {
                "audit_run_id": audit_run_id,
                "project_id": project_id,
                "agent_run_id": agent_run_id,
                "agent": template["name"],
                "payload": input_payload,
            },
        )

        manifest = {
            "audit_run_id": audit_run_id,
            "project_id": project_id,
            "agent_run_id": agent_run_id,
            "agent": template["name"],
            "model_profile": template.get("model_profile", "orchestrator-long-context"),
            "model_override_role": self._agent_role(template),
            "model_alias": model_alias,
            "runtime_config": "agent-runtime.json",
            "instructions": [f"instructions/{instruction_name}"],
            "mcp": sorted(mcp_servers),
        }
        if kimi_config:
            manifest["kimi_code_home"] = "."
            manifest["kimi_config"] = "config.toml"
        self._write_json(package_dir / "manifest.json", manifest)
        content_hash = self._hash_package(package_dir)
        await self._record(agent_run_id, package_dir, content_hash, manifest)
        return {
            "host_path": str(package_dir),
            "container_config_path": f"{template.get('runtime_mount', {}).get('target', '/dieaudit/runtime')}/agent-runtime.json",
            "content_hash": content_hash,
            "manifest": manifest,
        }

    def _runtime_config(
        self,
        template: dict[str, Any],
        mcp_config: dict[str, dict[str, Any]],
        instruction_target: Path,
    ) -> dict[str, Any]:
        profile_name = template.get("model_profile", "orchestrator-long-context")
        model_config = self._model_config(profile_name)
        return {
            "autoupdate": False,
            "model": model_config["model_ref"],
            "provider": model_config["providers"],
            "enabled_providers": [model_config["provider_name"]],
            "instructions": [f"./instructions/{instruction_target.name}"],
            "mcp": mcp_config,
            "tools": {
                "edit": True,
                "write": True,
            },
            "permission": {
                "edit": "allow",
                "bash": "allow",
                "webfetch": "allow",
            },
        }

    def _model_config(self, profile_name: str) -> dict[str, Any]:
        config_file = self.settings.config_root / "model-providers.yaml"
        with config_file.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        profiles = data.get("profiles", {})
        providers = data.get("providers", {})
        profile = profiles.get(profile_name) or {}
        provider_name = profile.get("provider") or next(iter(providers), "openai")
        provider = providers.get(provider_name, {})
        model = profile.get("model") or provider.get("default_model") or "gpt-4.1"

        provider_entry: dict[str, Any] = {
            "models": self._provider_models(provider, model),
            "options": {},
        }
        if provider.get("npm"):
            provider_entry["npm"] = provider["npm"]
        if provider.get("name"):
            provider_entry["name"] = provider["name"]
        api_key_env = provider.get("api_key_env")
        if api_key_env:
            provider_entry["options"]["apiKey"] = f"{{env:{api_key_env}}}"
        if provider.get("base_url"):
            provider_entry["options"]["baseURL"] = provider["base_url"]
        return {
            "provider_name": provider_name,
            "model_ref": f"{provider_name}/{model}",
            "raw_model": model,
            "api_key_env": api_key_env,
            "providers": {provider_name: provider_entry},
        }

    def _effective_model_config(self, template: dict[str, Any], input_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        base = self._model_config(template.get("model_profile", "orchestrator-long-context"))
        override = self._model_override(template, input_payload or {})
        if not override:
            provider = next(iter((base.get("providers") or {}).values()), {})
            return {
                **base,
                "provider_type": self._kimi_provider_type(str(base.get("provider_name") or "openai"), provider),
                "base_url": (provider.get("options") or {}).get("baseURL") or "",
                "api_key": self._api_key_from_env(base.get("api_key_env")),
                "context_window": self._first_model_limit(provider, str(base.get("raw_model") or ""), "context"),
                "max_output_tokens": self._first_model_limit(provider, str(base.get("raw_model") or ""), "output"),
            }

        provider_type = self._normalize_provider_type(override.get("provider_type") or override.get("provider") or "openai")
        model = str(override.get("model_name") or override.get("model") or base.get("raw_model") or "default")
        role = self._agent_role(template)
        provider_name = f"dieaudit-{role}".replace("_", "-")
        model_ref = f"{provider_name}/{model}"
        context_window = self._positive_int(override.get("context_window"), 128000)
        max_output_tokens = self._positive_int(override.get("max_output_tokens"), 8192)
        base_url = str(override.get("base_url") or "")
        api_key = str(override.get("api_key") or "")
        provider_entry: dict[str, Any] = {
            "models": {model: {"name": model, "limit": {"context": context_window, "output": max_output_tokens}}},
            "options": {},
            "type": provider_type,
        }
        if base_url:
            provider_entry["options"]["baseURL"] = base_url
        if api_key:
            provider_entry["options"]["apiKey"] = api_key
        return {
            **base,
            "provider_name": provider_name,
            "model_ref": model_ref,
            "raw_model": model,
            "api_key_env": None,
            "providers": {provider_name: provider_entry},
            "provider_type": provider_type,
            "base_url": base_url,
            "api_key": api_key,
            "context_window": context_window,
            "max_output_tokens": max_output_tokens,
            "temperature": override.get("temperature"),
            "override_role": role,
        }

    def _all_effective_model_configs(self, template: dict[str, Any], input_payload: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
        payload = input_payload or {}
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        overrides = config.get("model_overrides") if isinstance(config.get("model_overrides"), dict) else {}
        role = self._agent_role(template)
        result: dict[str, dict[str, Any]] = {}
        for override_role, override in sorted(overrides.items()):
            if isinstance(override, dict):
                result[str(override_role)] = self._effective_model_config_for_role(str(override_role), override, template)
        if role not in result:
            result[role] = self._effective_model_config(template, payload)
        return result

    def _effective_model_config_for_role(self, role: str, override: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
        base = self._model_config(template.get("model_profile", "orchestrator-long-context"))
        provider_type = self._normalize_provider_type(override.get("provider_type") or override.get("provider") or "openai")
        model = str(override.get("model_name") or override.get("model") or base.get("raw_model") or "default")
        provider_name = f"dieaudit-{role}".replace("_", "-")
        model_ref = self._model_alias_for_role(role)
        context_window = self._positive_int(override.get("context_window"), 128000)
        max_output_tokens = self._positive_int(override.get("max_output_tokens"), 8192)
        base_url = str(override.get("base_url") or "")
        api_key = str(override.get("api_key") or "")
        provider_entry: dict[str, Any] = {
            "models": {model: {"name": model, "limit": {"context": context_window, "output": max_output_tokens}}},
            "options": {},
            "type": provider_type,
        }
        if base_url:
            provider_entry["options"]["baseURL"] = base_url
        if api_key:
            provider_entry["options"]["apiKey"] = api_key
        return {
            **base,
            "provider_name": provider_name,
            "model_ref": model_ref,
            "raw_model": model,
            "api_key_env": None,
            "providers": {provider_name: provider_entry},
            "provider_type": provider_type,
            "base_url": base_url,
            "api_key": api_key,
            "context_window": context_window,
            "max_output_tokens": max_output_tokens,
            "temperature": override.get("temperature"),
            "override_role": role,
        }

    def _model_override(self, template: dict[str, Any], input_payload: dict[str, Any]) -> dict[str, Any]:
        config = input_payload.get("config") if isinstance(input_payload.get("config"), dict) else {}
        overrides = config.get("model_overrides") if isinstance(config.get("model_overrides"), dict) else {}
        role = self._agent_role(template)
        template_name = str(template.get("name") or "")
        for key in (role, template_name, template_name.replace("kimi-", "")):
            value = overrides.get(key)
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _provider_models(provider: dict[str, Any], model: str) -> dict[str, Any]:
        configured = provider.get("models") or {}
        models = dict(configured)
        if provider.get("type") == "custom" and model not in models:
            models[model] = {"name": model}
        return models

    def runtime_env(self, template: dict[str, Any], input_payload: dict[str, Any] | None = None, runtime_home: str | None = None) -> dict[str, str]:
        model_config = self._effective_model_config(template, input_payload or {})
        protocol = template.get("protocol") if isinstance(template.get("protocol"), dict) else {}
        if protocol.get("runtime") == "kimi":
            if runtime_home:
                return {
                    "KIMI_CODE_HOME": runtime_home,
                    "KIMI_DISABLE_TELEMETRY": "1",
                    "KIMI_CODE_NO_AUTO_UPDATE": "1",
                }
            provider = next(iter((model_config.get("providers") or {}).values()), {})
            provider_name = str(model_config.get("provider_name") or "kimi")
            model = str(model_config.get("raw_model") or model_config["model_ref"].split("/", 1)[-1])
            env = {
                "KIMI_MODEL_NAME": model,
                "KIMI_MODEL_PROVIDER_TYPE": self._kimi_provider_type(provider_name, provider),
                "KIMI_MODEL_API_KEY": "",
                "KIMI_MODEL_DISPLAY_NAME": str(model_config.get("model_ref") or model),
                "KIMI_DISABLE_TELEMETRY": "1",
                "KIMI_CODE_NO_AUTO_UPDATE": "1",
            }
            api_key_env = model_config.get("api_key_env")
            if api_key_env:
                api_key = os.environ.get(api_key_env, "")
                env["KIMI_MODEL_API_KEY"] = api_key
                env[str(api_key_env)] = api_key
            base_url = (provider.get("options") or {}).get("baseURL")
            if base_url:
                env["KIMI_MODEL_BASE_URL"] = str(base_url)
            if env["KIMI_MODEL_PROVIDER_TYPE"] == "openai":
                env["OPENAI_API_KEY"] = env["KIMI_MODEL_API_KEY"]
                if base_url:
                    env["OPENAI_BASE_URL"] = str(base_url)
            limits = ((provider.get("models") or {}).get(model) or {}).get("limit") or {}
            if limits.get("context"):
                env["KIMI_MODEL_MAX_CONTEXT_SIZE"] = str(limits["context"])
            return env
        api_key_env = model_config.get("api_key_env")
        if not api_key_env:
            return {}
        return {api_key_env: os.environ.get(api_key_env, "")}

    def kimi_config_toml(self, template: dict[str, Any], input_payload: dict[str, Any] | None = None) -> str:
        protocol = template.get("protocol") if isinstance(template.get("protocol"), dict) else {}
        if protocol.get("runtime") != "kimi":
            return ""
        model_configs = self._all_effective_model_configs(template, input_payload)
        default_model = self.model_alias_for_template(template, input_payload)

        lines = [
            "# Generated by DieAudit. Do not edit inside the runtime package.",
            f"default_model = {self._toml_string(default_model)}",
            "",
        ]
        for model_config in model_configs.values():
            provider_name = self._toml_key(str(model_config.get("provider_name") or "dieaudit"))
            provider_type = self._normalize_provider_type(model_config.get("provider_type") or "openai")
            base_url = str(model_config.get("base_url") or "")
            api_key = str(model_config.get("api_key") or "")
            lines.extend(
                [
                    f"[providers.{self._toml_string(provider_name)}]",
                    f"type = {self._toml_string(provider_type)}",
                ]
            )
            if base_url:
                lines.append(f"base_url = {self._toml_string(base_url)}")
            if api_key:
                lines.append(f"api_key = {self._toml_string(api_key)}")
            lines.append("")
        for model_config in model_configs.values():
            provider_name = self._toml_key(str(model_config.get("provider_name") or "dieaudit"))
            model_alias = self._toml_key(str(model_config.get("model_ref") or model_config.get("raw_model") or "dieaudit/default"))
            model = str(model_config.get("raw_model") or "default")
            context_window = self._positive_int(model_config.get("context_window"), 128000)
            max_output_tokens = self._positive_int(model_config.get("max_output_tokens"), 8192)
            lines.extend(
                [
                    f"[models.{self._toml_string(model_alias)}]",
                    f"provider = {self._toml_string(provider_name)}",
                    f"model = {self._toml_string(model)}",
                    f"max_context_size = {context_window}",
                    f"max_output_size = {max_output_tokens}",
                    "",
                ]
            )
        lines.extend(
            [
                "[permission]",
                'edit = "allow"',
                'bash = "allow"',
                'webfetch = "allow"',
                "",
                "[loop_control]",
                "max_steps_per_turn = 128",
                "",
            ]
        )
        return "\n".join(lines)

    def model_alias_for_template(self, template: dict[str, Any], input_payload: dict[str, Any] | None = None) -> str:
        role = self._agent_role(template)
        if self._model_override(template, input_payload or {}):
            return self._model_alias_for_role(role)
        return str(self._model_config(template.get("model_profile", "orchestrator-long-context")).get("model_ref") or "default")

    @staticmethod
    def _kimi_provider_type(provider_name: str, provider: dict[str, Any]) -> str:
        provider_type = str(provider.get("type") or provider_name).lower()
        npm = str(provider.get("npm") or "").lower()
        if "anthropic" in provider_type or "anthropic" in npm:
            return "anthropic"
        if "kimi" in provider_type or "moonshot" in provider_type or "kimi" in provider_name:
            return "kimi"
        return "openai"

    @staticmethod
    def _agent_role(template: dict[str, Any]) -> str:
        env = template.get("env") if isinstance(template.get("env"), dict) else {}
        return str(env.get("AGENT_ROLE") or template.get("role") or template.get("name") or "agent")

    @staticmethod
    def _normalize_provider_type(value: Any) -> str:
        provider_type = str(value or "openai").strip().lower().replace("-", "_")
        if provider_type not in {"openai", "openai_responses", "anthropic"}:
            return "openai"
        return provider_type

    @staticmethod
    def _model_alias_for_role(role: str) -> str:
        return f"dieaudit/{role}".replace("_", "-")

    @staticmethod
    def _api_key_from_env(api_key_env: Any) -> str:
        return os.environ.get(str(api_key_env), "") if api_key_env else ""

    @staticmethod
    def _first_model_limit(provider: dict[str, Any], model: str, key: str) -> int | None:
        limits = ((provider.get("models") or {}).get(model) or {}).get("limit") or {}
        value = limits.get(key)
        try:
            return int(value) if value else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _positive_int(value: Any, fallback: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        return parsed if parsed > 0 else fallback

    @staticmethod
    def _toml_key(value: str) -> str:
        return value.strip() or "dieaudit"

    @staticmethod
    def _toml_string(value: str) -> str:
        return json.dumps(str(value))

    @staticmethod
    def _mcp_config(mcp_servers: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for name, server in mcp_servers.items():
            if server.get("transport") == "stdio":
                continue
            else:
                result[name] = {
                    "type": "remote",
                    "url": server["url"],
                    "enabled": True,
                    "timeout": 5000,
                }
        return result

    def _package_dir(self, audit_run_id: str, agent_run_id: str) -> Path:
        return self.settings.artifact_root / "runtime-packages" / audit_run_id / agent_run_id

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _hash_package(path: Path) -> str:
        digest = hashlib.sha256()
        for file in sorted(path.rglob("*")):
            if file.is_file():
                digest.update(str(file.relative_to(path)).encode())
                digest.update(file.read_bytes())
        return digest.hexdigest()

    @staticmethod
    async def _record(agent_run_id: str, path: Path, content_hash: str, manifest: dict[str, Any]) -> None:
        async with SessionLocal() as session:
            existing = await session.scalar(select(RuntimePackage).where(RuntimePackage.agent_run_id == agent_run_id))
            if existing:
                existing.path = str(path)
                existing.content_hash = content_hash
                existing.manifest = manifest
            else:
                session.add(
                    RuntimePackage(
                        agent_run_id=agent_run_id,
                        path=str(path),
                        content_hash=content_hash,
                        manifest=manifest,
                    )
                )
            await session.commit()

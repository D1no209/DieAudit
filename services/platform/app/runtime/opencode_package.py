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


class OpenCodeRuntimePackageBuilder:
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
        opencode_config = self._opencode_config(template, mcp_config, instruction_target)
        self._write_json(package_dir / "opencode.json", opencode_config)
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
            "opencode_config": "opencode.json",
            "instructions": [f"instructions/{instruction_name}"],
            "mcp": sorted(mcp_servers),
        }
        self._write_json(package_dir / "manifest.json", manifest)
        content_hash = self._hash_package(package_dir)
        await self._record(agent_run_id, package_dir, content_hash, manifest)
        return {
            "host_path": str(package_dir),
            "container_config_path": f"{template.get('runtime_mount', {}).get('target', '/dieaudit/runtime')}/opencode.json",
            "content_hash": content_hash,
            "manifest": manifest,
        }

    def _opencode_config(
        self,
        template: dict[str, Any],
        mcp_config: dict[str, dict[str, Any]],
        instruction_target: Path,
    ) -> dict[str, Any]:
        profile_name = template.get("model_profile", "orchestrator-long-context")
        model_config = self._model_config(profile_name)
        return {
            "$schema": "https://opencode.ai/config.json",
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

    @staticmethod
    def _provider_models(provider: dict[str, Any], model: str) -> dict[str, Any]:
        configured = provider.get("models") or {}
        models = dict(configured)
        if provider.get("type") == "custom" and model not in models:
            models[model] = {"name": model}
        return models

    def runtime_env(self, template: dict[str, Any]) -> dict[str, str]:
        profile_name = template.get("model_profile", "orchestrator-long-context")
        model_config = self._model_config(profile_name)
        protocol = template.get("protocol") if isinstance(template.get("protocol"), dict) else {}
        if protocol.get("runtime") == "kimi":
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

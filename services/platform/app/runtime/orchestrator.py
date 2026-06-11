import json
import ntpath
import posixpath
import re
import uuid
import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from app.domain.models import AgentRun, AgentRunEvent, ApiKeyRecord, AuditRun, ContainerRun, Evidence, Finding, RuntimeNetwork, ValidationAttempt
from app.integrations.docker import DockerClient
from app.integrations.protocols import OpenCodeAcpClient
from app.repositories import SessionLocal
from app.runtime.opencode_package import OpenCodeRuntimePackageBuilder
from app.services.agent_output import AgentOutputIngestor
from app.services.auth import create_persisted_api_key
from app.services.templates import TemplateStore
from app.settings import Settings


def utc_ttl(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


class RuntimeOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.docker = DockerClient(settings.docker_host)
        self.agent_templates = TemplateStore(settings.config_root, "agent-templates", include_demo=settings.enable_demo_templates)
        self.mcp_templates = TemplateStore(settings.config_root, "mcp-templates", include_demo=settings.enable_demo_templates)
        self.opencode_packages = OpenCodeRuntimePackageBuilder(settings)
        self.opencode_client = OpenCodeAcpClient()
        self.agent_output_ingestor = AgentOutputIngestor()
        self._gateway_mounts: list[dict[str, Any]] | None = None

    async def close(self) -> None:
        await self.docker.close()

    async def docker_health(self) -> dict[str, Any]:
        ping = await self.docker.ping()
        version = await self.docker.version()
        return {"ok": ping == "OK", "ping": ping, "version": version}

    async def tool_image_capabilities(self, templates: list[dict[str, Any]]) -> dict[str, Any]:
        probes: dict[str, set[str]] = {}
        template_requirements: dict[str, dict[str, Any]] = {}
        for template in templates:
            required = [str(item) for item in template.get("required_binaries", []) if str(item).strip()]
            if not required:
                continue
            image = str(template.get("image") or "")
            name = str(template.get("name") or image)
            template_requirements[name] = {"image": image, "required_binaries": sorted(set(required))}
            probes.setdefault(image, set()).update(required)

        image_results: dict[str, Any] = {}
        for image, binaries in sorted(probes.items()):
            image_results[image] = await self._probe_image_binaries(image=image, binaries=sorted(binaries))

        templates_result: dict[str, Any] = {}
        for name, requirement in template_requirements.items():
            image = requirement["image"]
            image_result = image_results.get(image) or {}
            binaries_result = image_result.get("binaries") or {}
            missing = [
                binary
                for binary in requirement["required_binaries"]
                if not (binaries_result.get(binary) or {}).get("available")
            ]
            templates_result[name] = {
                **requirement,
                "available": not missing and bool(image_result.get("ok")),
                "missing_binaries": missing,
                "image_probe": image_result,
            }

        return {
            "ok": all(item.get("available") for item in templates_result.values()) if templates_result else True,
            "templates": templates_result,
            "images": image_results,
        }

    async def _probe_image_binaries(self, *, image: str, binaries: list[str]) -> dict[str, Any]:
        if not image:
            return {"ok": False, "image": image, "error": "template image is empty", "binaries": {}}
        if not await self.docker.image_exists(image):
            return {
                "ok": False,
                "image": image,
                "image_exists": False,
                "error": "image is not available locally; build or pull it before readiness probing",
                "binaries": {binary: {"available": False, "path": None} for binary in binaries},
            }
        script = (
            "import json, shutil, subprocess, sys\n"
            "tools=json.loads(sys.argv[1])\n"
            "def info(tool):\n"
            "    path=shutil.which(tool); data={'available': bool(path), 'path': path, 'version': None}\n"
            "    if not path: return data\n"
            "    for args in ([path, '--version'], [path, 'version']):\n"
            "        try:\n"
            "            p=subprocess.run(args, capture_output=True, text=True, timeout=10)\n"
            "        except Exception:\n"
            "            continue\n"
            "        out=(p.stdout or p.stderr or '').strip()\n"
            "        if p.returncode == 0 and out:\n"
            "            data['version']=out.splitlines()[0][:200]; break\n"
            "    return data\n"
            "print(json.dumps({'binaries': {tool: info(tool) for tool in tools}}))"
        )
        labels = {
            "dieaudit.managed": "true",
            "dieaudit.role": "tool-probe",
            "dieaudit.ttl": utc_ttl(hours=1),
        }
        try:
            result = await self.docker.run_ephemeral_container(
                name=f"{self.settings.dynamic_container_prefix}-tool-probe-{uuid.uuid4().hex[:8]}",
                image=image,
                command=["python", "-c", script, json.dumps(binaries)],
                labels=labels,
                timeout_seconds=30,
            )
        except Exception as exc:
            return {
                "ok": False,
                "image": image,
                "image_exists": True,
                "error": str(exc),
                "binaries": {binary: {"available": False, "path": None} for binary in binaries},
            }
        parsed = self._parse_probe_logs(result.get("logs") or "")
        probe_binaries = parsed.get("binaries") if isinstance(parsed, dict) else {}
        return {
            "ok": result.get("exit_code") == 0 and all((probe_binaries.get(binary) or {}).get("available") for binary in binaries),
            "image": image,
            "image_exists": True,
            "exit_code": result.get("exit_code"),
            "binaries": {
                binary: probe_binaries.get(binary, {"available": False, "path": None})
                for binary in binaries
            },
            "raw": parsed,
        }

    async def sandbox_capabilities(self) -> dict[str, Any]:
        try:
            ping = await self.docker.ping()
            info = await self.docker.info()
        except Exception as exc:
            requested_runtime = "runsc" if self.settings.enable_gvisor else self.settings.default_sandbox_runtime
            return {
                "ok": False,
                "docker_available": False,
                "default_runtime": self.settings.default_sandbox_runtime,
                "configured_gvisor": self.settings.enable_gvisor,
                "allow_runc_sandbox": self.settings.allow_runc_sandbox,
                "requested_runtime": requested_runtime,
                "gvisor_available": False,
                "strong_isolation_available": False,
                "sandbox_execution_available": False,
                "reason": str(exc),
            }
        runtimes = info.get("Runtimes") or {}
        runtime_names = sorted(runtimes.keys())
        default_runtime = str(info.get("DefaultRuntime") or self.settings.default_sandbox_runtime)
        requested_runtime = "runsc" if self.settings.enable_gvisor else self.settings.default_sandbox_runtime
        gvisor_available = "runsc" in runtimes
        requested_runtime_available = requested_runtime in runtimes or requested_runtime == default_runtime
        strong_isolation_available = requested_runtime != "runc" and requested_runtime_available
        docker_isolation_available = requested_runtime == "runc" and requested_runtime_available and self.settings.allow_runc_sandbox
        sandbox_execution_available = bool(ping == "OK" and requested_runtime_available and (strong_isolation_available or docker_isolation_available))
        reason = None
        if self.settings.enable_gvisor and not gvisor_available:
            reason = "gVisor is enabled but Docker runtime 'runsc' is not installed."
        elif not requested_runtime_available:
            reason = f"Configured sandbox runtime '{requested_runtime}' is not available in Docker."
        elif requested_runtime == "runc" and not self.settings.allow_runc_sandbox:
            reason = "Sandbox execution with the Docker runc runtime requires ALLOW_RUNC_SANDBOX=true."
        return {
            "ok": sandbox_execution_available,
            "docker_available": ping == "OK",
            "docker_default_runtime": default_runtime,
            "docker_runtimes": runtime_names,
            "configured_runtime": self.settings.default_sandbox_runtime,
            "configured_gvisor": self.settings.enable_gvisor,
            "allow_runc_sandbox": self.settings.allow_runc_sandbox,
            "requested_runtime": requested_runtime,
            "requested_runtime_available": requested_runtime_available,
            "strong_isolation_available": strong_isolation_available,
            "gvisor_available": gvisor_available,
            "sandbox_execution_available": sandbox_execution_available,
            "reason": reason,
            "warnings": self._sandbox_warnings(
                configured_gvisor=self.settings.enable_gvisor,
                allow_runc_sandbox=self.settings.allow_runc_sandbox,
                gvisor_available=gvisor_available,
                requested_runtime=requested_runtime,
                requested_runtime_available=requested_runtime_available,
            ),
        }

    async def managed_runtime(self) -> dict[str, Any]:
        containers = await self.docker.list_managed_containers()
        networks = await self.docker.list_managed_networks()
        now = datetime.now(timezone.utc)
        runs: dict[str, dict[str, Any]] = {}
        for container in containers:
            labels = container.get("Labels") or {}
            audit_run_id = labels.get("dieaudit.audit_run_id") or "unknown"
            run = runs.setdefault(audit_run_id, self._empty_managed_run(audit_run_id))
            item = self._managed_item_summary(container, labels, now)
            run["containers"].append(item)
            run["expired"] = bool(run["expired"] or item["expired"])
        for network in networks:
            labels = network.get("Labels") or {}
            audit_run_id = labels.get("dieaudit.audit_run_id") or "unknown"
            run = runs.setdefault(audit_run_id, self._empty_managed_run(audit_run_id))
            item = self._managed_item_summary(network, labels, now)
            run["networks"].append(item)
            run["expired"] = bool(run["expired"] or item["expired"])
        return {
            "containers": containers,
            "networks": networks,
            "runs": list(runs.values()),
            "summary": {
                "container_count": len(containers),
                "network_count": len(networks),
                "run_count": len(runs),
                "expired_run_count": sum(1 for run in runs.values() if run["expired"]),
            },
        }

    async def cleanup_expired_runtime(self) -> dict[str, Any]:
        state = await self.managed_runtime()
        expired_run_ids = [
            run["audit_run_id"]
            for run in state["runs"]
            if run["expired"] and run["audit_run_id"] != "unknown"
        ]
        cleanup_results = []
        for audit_run_id in sorted(set(expired_run_ids)):
            cleanup_results.append(await self.cleanup_run(audit_run_id))
        return {
            "expired_run_ids": sorted(set(expired_run_ids)),
            "cleanup_results": cleanup_results,
            "before": state["summary"],
        }

    async def start_agent_run(
        self,
        *,
        audit_run_id: str,
        project_id: str,
        agent_name: str,
        workspace_host_path: str | None = None,
        allow_external_network: bool = False,
        retain_runtime_on_failure: bool = False,
        input_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        network_name = f"{self.settings.dynamic_container_prefix}-run-{audit_run_id}"
        labels = self._labels(audit_run_id, project_id, role="runtime", ttl=utc_ttl())

        await self._ensure_agent_run_network(network_name, allow_external_network=allow_external_network, labels=labels)
        await self._connect_runtime_controllers(network_name)
        await self._record_network(audit_run_id, network_name, "created")

        agent = self.agent_templates.get(agent_name)
        protocol_kind = agent.get("protocol", {}).get("kind", "legacy-http")
        await self._record_agent_run(
            agent_run_id=run_id,
            audit_run_id=audit_run_id,
            project_id=project_id,
            agent_name=agent_name,
            template_name=agent.get("name", agent_name),
            protocol_kind=protocol_kind,
            status="starting",
            input_summary=input_payload or {},
        )
        mcp_results: list[dict[str, Any]] = []
        mcp_servers: dict[str, dict[str, str]] = {}

        try:
            for mcp_name in agent.get("required_mcp", []):
                mcp = self.mcp_templates.get(mcp_name)
                mcp_container = await self._start_mcp(
                    audit_run_id=audit_run_id,
                    project_id=project_id,
                    agent_run_id=run_id,
                    network_name=network_name,
                    workspace_host_path=workspace_host_path,
                    template=mcp,
                )
                mcp_results.append(mcp_container)
                if mcp.get("transport", "http") in {"http", "sse"}:
                    endpoint = mcp.get("mcp_endpoint", "")
                    mcp_servers[mcp["name"]] = {
                        "transport": mcp.get("transport", "http"),
                        "url": f"{self._mcp_base_url(mcp_container, mcp)}{endpoint}",
                    }

            runtime_package: dict[str, Any] | None = None
            if self._is_opencode_agent(agent):
                runtime_package = await self.opencode_packages.build(
                    audit_run_id=audit_run_id,
                    project_id=project_id,
                    agent_run_id=run_id,
                    template=agent,
                    mcp_servers=mcp_servers,
                    input_payload=input_payload or {},
                )

            agent_container = await self._start_agent(
                audit_run_id=audit_run_id,
                project_id=project_id,
                agent_run_id=run_id,
                network_name=network_name,
                workspace_host_path=workspace_host_path,
                runtime_host_path=runtime_package["host_path"] if runtime_package else None,
                runtime_config_path=runtime_package["container_config_path"] if runtime_package else None,
                template=agent,
                mcp_servers=mcp_servers,
                input_payload=input_payload or {},
            )
            opencode_result: dict[str, Any] | None = None
            structured_ingest: dict[str, Any] | None = None
            if runtime_package:
                opencode_result = await self._wait_for_opencode_agent(
                    audit_run_id=audit_run_id,
                    agent_run_id=run_id,
                    container_id=agent_container["id"],
                    artifact_dir=self._agent_artifact_dir(audit_run_id, run_id),
                )
                structured_ingest = await self.agent_output_ingestor.ingest(
                    agent_run_id=run_id,
                    audit_run_id=audit_run_id,
                    project_id=project_id,
                    payload=opencode_result,
                )
            if runtime_package:
                await self._record_agent_event(
                    run_id,
                    "runtime_package",
                    {
                        "path": runtime_package["host_path"],
                        "content_hash": runtime_package["content_hash"],
                        "manifest": runtime_package["manifest"],
                    },
                )
            final_status = "running"
            if opencode_result:
                final_status = "completed" if opencode_result.get("status") == "completed" else "failed"
            await self._record_agent_run(
                agent_run_id=run_id,
                audit_run_id=audit_run_id,
                project_id=project_id,
                agent_name=agent_name,
                template_name=agent.get("name", agent_name),
                protocol_kind=protocol_kind,
                status=final_status,
                input_summary=input_payload or {},
                output_summary={
                    "container_id": agent_container["id"],
                    "mcp_servers": mcp_servers,
                    "runtime_package": runtime_package,
                    "opencode_result": opencode_result,
                    "structured_ingest": structured_ingest,
                },
                artifact_path=opencode_result.get("artifact") if opencode_result else None,
                error=opencode_result.get("error") if opencode_result and opencode_result.get("status") == "failed" else None,
            )
            return {
                "run_id": run_id,
                "agent_run_id": run_id,
                "audit_run_id": audit_run_id,
                "project_id": project_id,
                "network": network_name,
                "agent": agent_container,
                "mcp": mcp_results,
                "mcp_servers": mcp_servers,
                "structured_ingest": structured_ingest,
                "opencode_status": opencode_result.get("status") if opencode_result else None,
            }
        except Exception as exc:
            await self._record_agent_run(
                agent_run_id=run_id,
                audit_run_id=audit_run_id,
                project_id=project_id,
                agent_name=agent_name,
                template_name=agent.get("name", agent_name),
                protocol_kind=protocol_kind,
                status="failed",
                input_summary=input_payload or {},
                error=str(exc),
            )
            if not retain_runtime_on_failure:
                await self.cleanup_run(audit_run_id)
            raise

    async def cleanup_run(self, audit_run_id: str) -> dict[str, Any]:
        containers = await self.docker.list_containers_by_run(audit_run_id)
        removed = []
        for container in containers:
            cid = container["Id"]
            removed.append({"id": cid, "names": container.get("Names", [])})
            exit_code = await self._container_exit_code(cid)
            log_artifact = await self._capture_container_logs(
                audit_run_id=audit_run_id,
                container_id=cid,
                container_name=(container.get("Names") or [None])[0],
                tail="all",
            )
            await self.docker.remove_container(cid, force=True)
            await self._mark_container_state(cid, "removed", exit_code=exit_code, log_artifact=log_artifact)

        removed_networks = []
        networks = await self.docker.list_networks_by_run(audit_run_id)
        if not networks:
            networks = [{"Name": f"{self.settings.dynamic_container_prefix}-run-{audit_run_id}"}]
        for network in networks:
            network_name = network.get("Name")
            if not network_name:
                continue
            await self._disconnect_runtime_controllers(network_name)
            await self.docker.remove_network(network_name)
            await self._mark_network_cleaned(audit_run_id, network_name)
            removed_networks.append(network_name)
        deactivated_api_keys = await self._deactivate_mcp_api_keys(audit_run_id)
        return {
            "audit_run_id": audit_run_id,
            "removed_containers": removed,
            "removed_networks": removed_networks,
            "deactivated_mcp_api_keys": deactivated_api_keys,
        }

    async def containers(self, audit_run_id: str) -> list[dict[str, Any]]:
        live_containers = await self.docker.list_containers_by_run(audit_run_id)
        live_by_id = {container.get("Id"): container for container in live_containers if container.get("Id")}
        rows: list[ContainerRun] = []
        async with SessionLocal() as session:
            rows = list(
                (
                    await session.execute(
                        select(ContainerRun).where(ContainerRun.audit_run_id == audit_run_id).order_by(ContainerRun.created_at.desc())
                    )
                ).scalars()
            )
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            live = live_by_id.get(row.container_id)
            merged.append(self._container_run_to_dict(row, live))
            seen.add(row.container_id)
        for container in live_containers:
            cid = container.get("Id")
            if cid and cid not in seen:
                merged.append(container)
        return merged

    async def logs(self, audit_run_id: str, container_id: str) -> str:
        try:
            return await self.docker.logs(container_id, tail=1000)
        except Exception:
            async with SessionLocal() as session:
                row = await session.scalar(
                    select(ContainerRun).where(
                        ContainerRun.audit_run_id == audit_run_id,
                        ContainerRun.container_id == container_id,
                    )
                )
            if row and row.log_artifact:
                path = Path(row.log_artifact)
                if path.exists():
                    return path.read_text(encoding="utf-8", errors="replace")
            raise

    async def run_mcp_tool(
        self,
        *,
        audit_run_id: str,
        project_id: str,
        mcp_name: str,
        tool_path: str,
        workspace_host_path: str | None,
        payload: dict[str, Any] | None = None,
        allow_external_network: bool = False,
        retain_runtime_on_failure: bool = False,
    ) -> dict[str, Any]:
        tool_run_id = str(uuid.uuid4())
        dedicated_network = allow_external_network
        network_name = (
            f"{self.settings.dynamic_container_prefix}-run-{audit_run_id}-tool-{tool_run_id[:8]}"
            if dedicated_network
            else f"{self.settings.dynamic_container_prefix}-run-{audit_run_id}"
        )
        labels = self._labels(audit_run_id, project_id, role="runtime", ttl=utc_ttl())
        await self.docker.create_network(network_name, internal=not allow_external_network, labels=labels)
        await self._connect_runtime_controllers(network_name)
        await self._record_network(audit_run_id, network_name, "created")
        template = self.mcp_templates.get(mcp_name)
        container: dict[str, Any] | None = None
        container_cleaned = False
        tool_succeeded = False
        try:
            container = await self._start_mcp(
                audit_run_id=audit_run_id,
                project_id=project_id,
                agent_run_id=f"tool-{tool_run_id}",
                network_name=network_name,
                workspace_host_path=workspace_host_path,
                template=template,
            )
            url = f"{self._mcp_base_url(container, template)}{tool_path}"
            async with httpx.AsyncClient(timeout=template.get("tool_timeout_seconds", 900), trust_env=False) as client:
                response = await client.post(url, json=payload or {})
            if response.status_code >= 400:
                raise RuntimeError(f"{mcp_name} {tool_path} failed: {response.status_code} {response.text}")
            result = response.json()
            tool_succeeded = True
            return {"ok": True, "mcp": container, "result": result}
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
        finally:
            should_retain = bool(retain_runtime_on_failure and not tool_succeeded)
            if not should_retain and container and not container_cleaned:
                await self._capture_and_remove_container(
                    audit_run_id=audit_run_id,
                    container_id=container["id"],
                    container_name=container.get("name"),
                )
                container_cleaned = True
            if dedicated_network and not should_retain:
                await self._disconnect_runtime_controllers(network_name)
                await self.docker.remove_network(network_name)
                await self._mark_network_cleaned(audit_run_id, network_name)

    async def run_poc_container(
        self,
        *,
        audit_run_id: str,
        project_id: str,
        image: str,
        command: list[str],
        env: dict[str, str] | None = None,
        workspace_host_path: str | None = None,
        allow_external_network: bool = False,
        retain_runtime_on_failure: bool = False,
        timeout_seconds: int = 120,
        mount_workspace: bool = True,
        network_name: str | None = None,
        target_url: str | None = None,
        allow_weak_isolation: bool = False,
    ) -> dict[str, Any]:
        capabilities = await self._require_sandbox_execution(allow_weak_isolation=allow_weak_isolation)

        poc_run_id = str(uuid.uuid4())
        dedicated_network = network_name is None
        network_name = network_name or f"{self.settings.dynamic_container_prefix}-run-{audit_run_id}-poc-{poc_run_id[:8]}"
        labels = self._labels(audit_run_id, project_id, role="poc", ttl=utc_ttl(hours=4))
        labels["dieaudit.poc_run_id"] = poc_run_id
        labels["dieaudit.sandbox_runtime"] = str(capabilities.get("requested_runtime") or self.settings.default_sandbox_runtime)
        if dedicated_network:
            await self.docker.create_network(network_name, internal=not allow_external_network, labels=labels)
            await self._record_network(audit_run_id, network_name, "created")
        else:
            await self._require_managed_run_network(network_name=network_name, audit_run_id=audit_run_id)

        mounts: list[dict[str, Any]] = []
        if mount_workspace and workspace_host_path:
            mounts.append(self._bind_mount(await self._host_path_for(Path(workspace_host_path)), "/workspace", read_only=True))

        artifact_dir = self.settings.artifact_root / "poc-runs" / audit_run_id / poc_run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        mounts.append(self._bind_mount(await self._host_path_for(artifact_dir), "/artifacts", read_only=False))

        runtime_name = str(capabilities.get("requested_runtime") or self.settings.default_sandbox_runtime)
        payload = self._container_payload(
            image=image,
            command=command,
            env={
                **(env or {}),
                "AUDIT_RUN_ID": audit_run_id,
                "PROJECT_ID": project_id,
                "POC_RUN_ID": poc_run_id,
                "ARTIFACT_DIR": "/artifacts",
                **({"TARGET_URL": target_url} if target_url else {}),
            },
            labels=labels,
            network_name=network_name,
            aliases=[f"poc-{poc_run_id[:8]}"],
            mounts=mounts,
            read_only=True,
            healthcheck=None,
            runtime=runtime_name if runtime_name != "runc" else None,
            resources={
                "memory": "512m",
                "cpus": 1.0,
                "pids_limit": 256,
                "tmpfs": {"/tmp": "rw,noexec,nosuid,size=64m"},
            },
        )

        await self.docker.pull_image(image)
        name = self._runtime_container_name(
            audit_run_id=audit_run_id,
            role="poc",
            template_name="poc",
            run_id=poc_run_id,
        )
        created: dict[str, Any] | None = None
        log_artifact: str | None = None
        status = "created"
        exit_code: int | None = None
        wait_result: dict[str, Any] | None = None
        try:
            created = await self.docker.create_container(name, payload)
            await self._record_container(audit_run_id, project_id, None, created["Id"], name, image, "poc", labels, "created")
            await self.docker.start_container(created["Id"])
            await self._mark_container_state(created["Id"], "running")
            try:
                wait_result = await asyncio.wait_for(self.docker.wait_container(created["Id"]), timeout=timeout_seconds)
                exit_code = int(wait_result.get("StatusCode") or 0)
                status = "completed" if exit_code == 0 else "failed"
            except asyncio.TimeoutError:
                status = "timeout"
                await self.docker.stop_container(created["Id"], timeout_seconds=1)
            log_artifact = await self._capture_container_logs(
                audit_run_id=audit_run_id,
                container_id=created["Id"],
                container_name=name,
                tail="all",
            )
            await self._mark_container_state(created["Id"], status, exit_code=exit_code, log_artifact=log_artifact)
            result = {
                "ok": status == "completed",
                "poc_run_id": poc_run_id,
                "audit_run_id": audit_run_id,
                "project_id": project_id,
                "container": {
                    "id": created["Id"],
                    "name": name,
                    "image": image,
                    "role": "poc",
                    "status": status,
                    "exit_code": exit_code,
                    "log_artifact": log_artifact,
                },
                "network": network_name,
                "network_reused": not dedicated_network,
                "target_url": target_url,
                "wait_result": wait_result,
                "artifact_dir": str(artifact_dir),
                "sandbox": capabilities,
            }
            return result
        finally:
            if created and not retain_runtime_on_failure:
                with contextlib.suppress(Exception):
                    if log_artifact is None:
                        log_artifact = await self._capture_container_logs(
                            audit_run_id=audit_run_id,
                            container_id=created["Id"],
                            container_name=name,
                            tail="all",
                        )
                    await self.docker.remove_container(created["Id"], force=True)
                    await self._mark_container_state(created["Id"], "removed", exit_code=exit_code, log_artifact=log_artifact)
            if dedicated_network and not retain_runtime_on_failure:
                await self.docker.remove_network(network_name)
                await self._mark_network_cleaned(audit_run_id, network_name)

    async def start_sandbox_service(
        self,
        *,
        audit_run_id: str,
        project_id: str,
        image: str,
        command: list[str],
        env: dict[str, str] | None = None,
        workspace_host_path: str | None = None,
        service_name: str = "target",
        port: int = 8080,
        allow_external_network: bool = False,
        retain_runtime_on_failure: bool = True,
        startup_timeout_seconds: int = 30,
        mount_workspace: bool = True,
        healthcheck_path: str | None = None,
        allow_weak_isolation: bool = False,
    ) -> dict[str, Any]:
        capabilities = await self._require_sandbox_execution(allow_weak_isolation=allow_weak_isolation)

        sandbox_id = str(uuid.uuid4())
        network_name = f"{self.settings.dynamic_container_prefix}-run-{audit_run_id}-sandbox"
        network_labels = self._labels(audit_run_id, project_id, role="sandbox", ttl=utc_ttl(hours=8))
        network_labels["dieaudit.sandbox_runtime"] = str(capabilities.get("requested_runtime") or self.settings.default_sandbox_runtime)
        _, created_network = await self._ensure_managed_run_network(
            network_name=network_name,
            audit_run_id=audit_run_id,
            project_id=project_id,
            role="sandbox",
            allow_external_network=allow_external_network,
            labels=network_labels,
        )
        labels = dict(network_labels)
        labels["dieaudit.sandbox_id"] = sandbox_id
        labels["dieaudit.sandbox_service"] = service_name

        mounts: list[dict[str, Any]] = []
        if mount_workspace and workspace_host_path:
            mounts.append(self._bind_mount(await self._host_path_for(Path(workspace_host_path)), "/workspace", read_only=True))
        artifact_dir = self.settings.artifact_root / "sandbox-services" / audit_run_id / sandbox_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        mounts.append(self._bind_mount(await self._host_path_for(artifact_dir), "/artifacts", read_only=False))

        healthcheck = None
        if healthcheck_path:
            healthcheck = {
                "Test": ["CMD-SHELL", f"python - <<'PY'\nimport urllib.request\nurllib.request.urlopen('http://127.0.0.1:{port}{healthcheck_path}', timeout=2).read(1)\nPY"],
                "Interval": 2_000_000_000,
                "Timeout": 2_000_000_000,
                "Retries": max(1, startup_timeout_seconds // 2),
            }
        runtime_name = str(capabilities.get("requested_runtime") or self.settings.default_sandbox_runtime)
        payload = self._container_payload(
            image=image,
            command=command,
            env={
                **(env or {}),
                "AUDIT_RUN_ID": audit_run_id,
                "PROJECT_ID": project_id,
                "SANDBOX_ID": sandbox_id,
                "SERVICE_NAME": service_name,
                "SERVICE_PORT": str(port),
                "ARTIFACT_DIR": "/artifacts",
            },
            labels=labels,
            network_name=network_name,
            aliases=[service_name, f"sandbox-{sandbox_id[:8]}"],
            mounts=mounts,
            read_only=True,
            healthcheck=healthcheck,
            runtime=runtime_name if runtime_name != "runc" else None,
            resources={
                "memory": "768m",
                "cpus": 1.0,
                "pids_limit": 512,
                "tmpfs": {"/tmp": "rw,nosuid,size=128m"},
            },
        )

        await self.docker.pull_image(image)
        name = self._runtime_container_name(
            audit_run_id=audit_run_id,
            role="sandbox",
            template_name=service_name,
            run_id=sandbox_id,
        )
        created: dict[str, Any] | None = None
        try:
            created = await self.docker.create_container(name, payload)
            await self._record_container(audit_run_id, project_id, None, created["Id"], name, image, "sandbox", labels, "created")
            await self.docker.start_container(created["Id"])
            await self._mark_container_state(created["Id"], "starting")
            await self.docker.wait_for_healthy(created["Id"], timeout_seconds=startup_timeout_seconds)
            await self._mark_container_state(created["Id"], "running")
            return {
                "ok": True,
                "sandbox_id": sandbox_id,
                "audit_run_id": audit_run_id,
                "project_id": project_id,
                "network": network_name,
                "service_name": service_name,
                "port": port,
                "target_url": f"http://{service_name}:{port}",
                "artifact_dir": str(artifact_dir),
                "container": {
                    "id": created["Id"],
                    "name": name,
                    "image": image,
                    "role": "sandbox",
                    "status": "running",
                },
                "sandbox": capabilities,
            }
        except Exception:
            if created:
                with contextlib.suppress(Exception):
                    log_artifact = await self._capture_container_logs(
                        audit_run_id=audit_run_id,
                        container_id=created["Id"],
                        container_name=name,
                        tail="all",
                    )
                    await self._mark_container_state(created["Id"], "failed", log_artifact=log_artifact)
                    if not retain_runtime_on_failure:
                        await self.docker.remove_container(created["Id"], force=True)
                        await self._mark_container_state(created["Id"], "removed", log_artifact=log_artifact)
            if created_network and not retain_runtime_on_failure:
                await self.docker.remove_network(network_name)
                await self._mark_network_cleaned(audit_run_id, network_name)
            raise

    async def scale_validators(
        self,
        *,
        audit_run_id: str,
        project_id: str,
        findings: list[dict[str, Any]],
        workspace_host_path: str | None,
        validator_rounds: int,
        max_parallel_validators: int,
        validator_agent_name: str,
        allow_external_network: bool,
        retain_runtime_on_failure: bool,
        wait_for_completion: bool = False,
        cancel_requested: Callable[[], Awaitable[bool]] | None = None,
        cancel_reason: Callable[[], Awaitable[str | None]] | None = None,
    ) -> dict[str, Any]:
        await self._record_audit_run(
            audit_run_id=audit_run_id,
            project_id=project_id,
            validator_rounds=validator_rounds,
            max_parallel_validators=max_parallel_validators,
            allow_external_network=allow_external_network,
            retain_runtime_on_failure=retain_runtime_on_failure,
            config={
                "validator_agent_name": validator_agent_name,
                "finding_count": len(findings),
            },
        )
        if not findings:
            return {
                "audit_run_id": audit_run_id,
                "status": "accepted",
                "scheduled": 0,
                "note": "No findings were provided.",
            }

        semaphore = asyncio.Semaphore(max(1, int(max_parallel_validators)))

        async def validator_cancel_state() -> tuple[bool, str | None]:
            if cancel_requested is None:
                return False, None
            if not await cancel_requested():
                return False, None
            reason = await cancel_reason() if cancel_reason is not None else None
            return True, reason or "cancel_requested"

        async def record_cancelled_attempt(
            *,
            attempt_id: str,
            finding_id: str,
            finding: dict[str, Any],
            round_index: int,
            reason: str,
        ) -> dict[str, Any]:
            result = {"finding": finding, "reason": reason, "round": round_index}
            await self._record_validation_attempt(
                attempt_id=attempt_id,
                finding_id=finding_id,
                audit_run_id=audit_run_id,
                round_index=round_index,
                status="cancelled",
                result=result,
            )
            await self._record_validation_evidence(
                finding_id=finding_id,
                audit_run_id=audit_run_id,
                kind="validator-cancelled",
                summary=f"Validator round {round_index} was cancelled before starting an AgentRun.",
                payload=result,
            )
            return {"status": "cancelled", "finding_id": finding_id, "round": round_index, "reason": reason}

        async def run_validator(finding: dict[str, Any], round_index: int) -> dict[str, Any]:
            finding_id = str(finding.get("finding_id") or finding.get("id") or f"inline-{uuid.uuid4()}")
            attempt_id = str(uuid.uuid4())
            await self._record_validation_attempt(
                attempt_id=attempt_id,
                finding_id=finding_id,
                audit_run_id=audit_run_id,
                round_index=round_index,
                status="queued",
                result={"finding": finding},
            )
            cancelled, reason = await validator_cancel_state()
            if cancelled:
                return await record_cancelled_attempt(
                    attempt_id=attempt_id,
                    finding_id=finding_id,
                    finding=finding,
                    round_index=round_index,
                    reason=reason or "cancel_requested",
                )
            async with semaphore:
                cancelled, reason = await validator_cancel_state()
                if cancelled:
                    return await record_cancelled_attempt(
                        attempt_id=attempt_id,
                        finding_id=finding_id,
                        finding=finding,
                        round_index=round_index,
                        reason=reason or "cancel_requested",
                    )
                await self._record_validation_attempt(
                    attempt_id=attempt_id,
                    finding_id=finding_id,
                    audit_run_id=audit_run_id,
                    round_index=round_index,
                    status="running",
                    result={"finding": finding},
                )
                payload = {
                    "goal": "Validate the supplied finding and produce evidence, confidence, and next steps.",
                    "finding": finding,
                    "round": round_index,
                    "validator_rounds": validator_rounds,
                }
                try:
                    result = await self.start_agent_run(
                        audit_run_id=audit_run_id,
                        project_id=project_id,
                        agent_name=validator_agent_name,
                        workspace_host_path=workspace_host_path,
                        allow_external_network=allow_external_network,
                        retain_runtime_on_failure=retain_runtime_on_failure,
                        input_payload=payload,
                    )
                except Exception as exc:
                    await self._record_validation_attempt(
                        attempt_id=attempt_id,
                        finding_id=finding_id,
                        audit_run_id=audit_run_id,
                        round_index=round_index,
                        status="failed",
                        result={"finding": finding, "error": str(exc)},
                    )
                    await self._record_validation_evidence(
                        finding_id=finding_id,
                        audit_run_id=audit_run_id,
                        kind="validator-error",
                        summary=f"Validator round {round_index} failed: {exc}",
                        payload={"round": round_index, "error": str(exc), "finding": finding},
                    )
                    raise
                agent_run_id = str(result.get("agent_run_id") or result.get("run_id") or "")
                await self._record_validation_attempt(
                    attempt_id=attempt_id,
                    finding_id=finding_id,
                    audit_run_id=audit_run_id,
                    round_index=round_index,
                    status="completed",
                    agent_run_id=agent_run_id or None,
                    result={"finding": finding, "agent_run": result},
                )
                await self._record_validation_evidence(
                    finding_id=finding_id,
                    audit_run_id=audit_run_id,
                    kind="validator-agent-run",
                    summary=f"Validator round {round_index} completed with AgentRun {agent_run_id or 'unknown'}.",
                    payload={"round": round_index, "agent_run_id": agent_run_id, "result": result},
                )
                return {"status": "completed", "finding_id": finding_id, "round": round_index, "result": result}

        scheduled: list[asyncio.Task] = []
        await self._mark_findings_status([str(finding.get("finding_id")) for finding in findings if finding.get("finding_id")], "validating")
        for finding in findings:
            for round_index in range(1, validator_rounds + 1):
                scheduled.append(asyncio.create_task(run_validator(finding, round_index)))

        async def drain(tasks: list[asyncio.Task]) -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            for task in asyncio.as_completed(tasks):
                try:
                    results.append(await task)
                except Exception as exc:
                    results.append({"status": "failed", "error": str(exc)})
            return results

        results: list[dict[str, Any]] = []
        if wait_for_completion:
            results = await drain(scheduled)
        else:
            asyncio.create_task(drain(scheduled))
        status_counts: dict[str, int] = {}
        for result in results:
            status = str(result.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        return {
            "audit_run_id": audit_run_id,
            "project_id": project_id,
            "status": "accepted",
            "scheduled": len(scheduled),
            "validator_rounds": validator_rounds,
            "max_parallel_validators": max_parallel_validators,
            "validator_agent_name": validator_agent_name,
            "results": results if wait_for_completion else [],
            "status_counts": status_counts,
        }

    async def _start_mcp(
        self,
        *,
        audit_run_id: str,
        project_id: str,
        agent_run_id: str,
        network_name: str,
        workspace_host_path: str | None,
        template: dict[str, Any],
    ) -> dict[str, Any]:
        image = template["image"]
        await self.docker.pull_image(image)
        name = self._runtime_container_name(
            audit_run_id=audit_run_id,
            role="mcp",
            template_name=template["name"],
            run_id=agent_run_id,
        )
        labels = self._labels(audit_run_id, project_id, role="mcp", ttl=utc_ttl())
        labels["dieaudit.mcp"] = template["name"]
        labels["dieaudit.agent_run_id"] = agent_run_id

        if template["name"] == "joern-mcp":
            mcp_artifact_path = self.settings.artifact_root / "joern" / audit_run_id
        else:
            mcp_artifact_path = self.settings.artifact_root / "mcp-runs" / audit_run_id / agent_run_id / template["name"]
        mcp_artifact_path.mkdir(parents=True, exist_ok=True)
        mounts = await self._mounts(workspace_host_path, template, artifact_host_path=mcp_artifact_path)
        env = await self._mcp_env(
            template=template,
            audit_run_id=audit_run_id,
            project_id=project_id,
            agent_run_id=agent_run_id,
        )
        payload = self._container_payload(
            image=image,
            command=template.get("command"),
            env=env,
            labels=labels,
            network_name=network_name,
            aliases=[name, template["name"]],
            mounts=mounts,
            read_only=template.get("read_only", True),
            healthcheck=None,
            resources=template.get("resources"),
        )
        created = await self.docker.create_container(name, payload)
        await self.docker.start_container(created["Id"])
        await self._record_container(audit_run_id, project_id, agent_run_id, created["Id"], name, image, "mcp", labels, "starting")
        await self._wait_for_mcp_http(name, template, timeout_seconds=template.get("health_timeout_seconds", 45))
        await self._record_container(audit_run_id, project_id, agent_run_id, created["Id"], name, image, "mcp", labels, "running")
        return {"id": created["Id"], "name": name, "host": name, "image": image, "role": "mcp", "template": template["name"]}

    async def _mcp_env(self, *, template: dict[str, Any], audit_run_id: str, project_id: str, agent_run_id: str) -> dict[str, Any]:
        env = {
            **template.get("env", {}),
            "AUDIT_RUN_ID": audit_run_id,
            "PROJECT_ID": project_id,
        }
        if template.get("permissions", {}).get("platform_api"):
            env.setdefault("PLATFORM_API_URL", "http://agent-gateway:8000")
            env.setdefault("KNOWLEDGE_API_URL", env["PLATFORM_API_URL"])
            env["API_KEY_HEADER"] = self.settings.api_key_header
            env["DIEAUDIT_API_KEY"] = await self._create_mcp_api_key(
                template=template,
                audit_run_id=audit_run_id,
                project_id=project_id,
                agent_run_id=agent_run_id,
            )
        self._inject_internal_no_proxy(env, ["agent-gateway", "host.docker.internal"])
        return env

    async def _create_mcp_api_key(self, *, template: dict[str, Any], audit_run_id: str, project_id: str, agent_run_id: str) -> str:
        platform_api = str(template.get("permissions", {}).get("platform_api") or "")
        scopes = ["read"] if platform_api == "knowledge" else ["audit"]
        result = await create_persisted_api_key(
            name=f"mcp-{template['name']}-{audit_run_id}-{agent_run_id[:8]}",
            scopes=scopes,
            metadata={
                "kind": "mcp-sidecar",
                "mcp": template["name"],
                "agent_run_id": agent_run_id,
                "project_ids": [project_id],
                "audit_run_ids": [audit_run_id],
                "expires_at": utc_ttl(),
            },
            default_scope=scopes[0],
        )
        return result["api_key"]

    async def _deactivate_mcp_api_keys(self, audit_run_id: str) -> list[str]:
        deactivated: list[str] = []
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(ApiKeyRecord).where(
                        ApiKeyRecord.status == "active",
                    )
                )
            ).scalars()
            now = datetime.now(timezone.utc)
            for row in rows:
                metadata = row.metadata_json or {}
                if metadata.get("kind") != "mcp-sidecar":
                    continue
                audit_run_ids = metadata.get("audit_run_ids") or []
                if audit_run_id not in {str(item) for item in audit_run_ids}:
                    continue
                row.status = "inactive"
                row.deactivated_at = now
                deactivated.append(row.key_id)
            await session.commit()
        return deactivated

    async def _start_agent(
        self,
        *,
        audit_run_id: str,
        project_id: str,
        agent_run_id: str,
        network_name: str,
        workspace_host_path: str | None,
        runtime_host_path: str | None,
        runtime_config_path: str | None,
        template: dict[str, Any],
        mcp_servers: dict[str, dict[str, str]],
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        image = template["image"]
        await self.docker.pull_image(image)
        name = self._runtime_container_name(
            audit_run_id=audit_run_id,
            role="agent",
            template_name=template["name"],
            run_id=agent_run_id,
        )
        labels = self._labels(audit_run_id, project_id, role="agent", ttl=utc_ttl())
        labels["dieaudit.agent"] = template["name"]
        labels["dieaudit.agent_run_id"] = agent_run_id

        env = {
            **template.get("env", {}),
            "AUDIT_RUN_ID": audit_run_id,
            "PROJECT_ID": project_id,
            "AGENT_RUN_ID": agent_run_id,
            "AGENT_GATEWAY_URL": "http://agent-gateway:8000",
            "MCP_SERVERS_JSON": json.dumps(mcp_servers),
            "AGENT_INPUT_JSON": json.dumps(input_payload),
        }
        self._inject_no_proxy(env, mcp_servers)
        if runtime_config_path:
            env["OPENCODE_CONFIG"] = runtime_config_path
            env["DIEAUDIT_RUNTIME_DIR"] = str(Path(runtime_config_path).parent)
            env.update(self.opencode_client.command_env())
            env.update(self.opencode_packages.runtime_env(template))
        mounts = await self._mounts(workspace_host_path, template)
        artifact_host_path = self._agent_artifact_dir(audit_run_id, agent_run_id)
        artifact_target = template.get("artifact_mount", {}).get("target", "/artifacts")
        artifact_host_path.mkdir(parents=True, exist_ok=True)
        mounts.append(self._bind_mount(await self._host_path_for(artifact_host_path), artifact_target, read_only=False))
        env["ARTIFACT_DIR"] = artifact_target
        if runtime_host_path:
            target = template.get("runtime_mount", {}).get("target", "/dieaudit/runtime")
            mounts.append(self._bind_mount(await self._host_path_for(Path(runtime_host_path)), target, read_only=True))
        payload = self._container_payload(
            image=image,
            command=template.get("command"),
            env=env,
            labels=labels,
            network_name=network_name,
            aliases=[name, template["name"]],
            mounts=mounts,
            read_only=template.get("read_only", True),
            healthcheck=template.get("healthcheck"),
            resources=template.get("resources"),
        )
        created = await self.docker.create_container(name, payload)
        await self.docker.start_container(created["Id"])
        await self._record_container(audit_run_id, project_id, agent_run_id, created["Id"], name, image, "agent", labels, "running")
        return {"id": created["Id"], "name": name, "image": image, "role": "agent", "template": template["name"]}

    async def _wait_for_opencode_agent(
        self,
        *,
        audit_run_id: str,
        agent_run_id: str,
        container_id: str,
        artifact_dir: Path,
    ) -> dict[str, Any]:
        wait_error: str | None = None
        try:
            wait_result = await asyncio.wait_for(
                self.docker.wait_container(container_id),
                timeout=getattr(self.settings, "opencode_agent_timeout_seconds", 600),
            )
        except asyncio.TimeoutError:
            wait_error = f"OpenCode agent timed out after {getattr(self.settings, 'opencode_agent_timeout_seconds', 600)}s"
            await self.docker.stop_container(container_id, timeout_seconds=3)
            wait_result = {"StatusCode": 124, "error": wait_error}
        except Exception as exc:
            wait_error = str(exc)
            wait_result = {"StatusCode": 1, "error": wait_error}
        status_code = int(wait_result.get("StatusCode") or 0)
        log_artifact = await self._capture_container_logs(
            audit_run_id=audit_run_id,
            container_id=container_id,
            tail="all",
        )
        await self._mark_container_state(
            container_id,
            "completed" if status_code == 0 else "failed",
            exit_code=status_code,
            log_artifact=log_artifact,
        )
        result_file = artifact_dir / "agent_result.json"
        payload: dict[str, Any] = {
            "status": "failed",
            "wait_result": wait_result,
            "artifact": str(result_file),
            "log_artifact": log_artifact,
        }
        if wait_error:
            payload["error"] = wait_error
        if result_file.exists():
            try:
                payload.update(json.loads(result_file.read_text(encoding="utf-8")))
            except json.JSONDecodeError as exc:
                payload["error"] = f"invalid agent_result.json: {exc}"
        elif not wait_error:
            payload["error"] = "agent_result.json not found"

        for event in payload.get("events", []):
            await self._record_agent_event(agent_run_id, event.get("event_type", "acp_event"), event)
        await self._record_agent_event(agent_run_id, "opencode_result", payload)
        return payload

    async def _capture_and_remove_container(
        self,
        *,
        audit_run_id: str,
        container_id: str,
        container_name: str | None = None,
    ) -> str | None:
        exit_code = await self._container_exit_code(container_id)
        log_artifact = await self._capture_container_logs(
            audit_run_id=audit_run_id,
            container_id=container_id,
            container_name=container_name,
            tail="all",
        )
        await self.docker.remove_container(container_id, force=True)
        await self._mark_container_state(container_id, "removed", exit_code=exit_code, log_artifact=log_artifact)
        return log_artifact

    async def _container_exit_code(self, container_id: str) -> int | None:
        try:
            info = await self.docker.inspect_container(container_id)
        except Exception:
            return None
        state = info.get("State") or {}
        exit_code = state.get("ExitCode")
        return int(exit_code) if exit_code is not None else None

    async def _capture_container_logs(
        self,
        *,
        audit_run_id: str,
        container_id: str,
        container_name: str | None = None,
        tail: int | str = "all",
    ) -> str | None:
        log_dir = self.settings.artifact_root / "container-logs" / audit_run_id
        log_dir.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_artifact_name(container_name or container_id[:12])
        log_path = log_dir / f"{safe_name}-{container_id[:12]}.log"
        try:
            content = await self.docker.logs(container_id, tail=tail)
        except Exception as exc:
            content = f"Failed to read Docker logs before cleanup: {exc}\n"
        log_path.write_text(content or "", encoding="utf-8", errors="replace")
        return str(log_path)

    async def _mark_container_state(
        self,
        container_id: str,
        status: str,
        *,
        exit_code: int | None = None,
        log_artifact: str | None = None,
    ) -> None:
        async with SessionLocal() as session:
            row = await session.scalar(select(ContainerRun).where(ContainerRun.container_id == container_id))
            if row:
                row.status = status
                if exit_code is not None:
                    row.exit_code = exit_code
                if log_artifact:
                    row.log_artifact = log_artifact
            await session.commit()

    async def _record_container(
        self,
        audit_run_id: str,
        project_id: str,
        agent_run_id: str | None,
        container_id: str,
        container_name: str | None,
        image: str,
        role: str,
        labels: dict[str, str],
        status: str,
    ) -> None:
        async with SessionLocal() as session:
            existing = await session.scalar(select(ContainerRun).where(ContainerRun.container_id == container_id))
            if existing:
                existing.status = status
                existing.labels = labels
                existing.agent_run_id = agent_run_id
                existing.container_name = container_name
            else:
                session.add(
                    ContainerRun(
                        audit_run_id=audit_run_id,
                        project_id=project_id,
                        agent_run_id=agent_run_id,
                        container_id=container_id,
                        container_name=container_name,
                        image=image,
                        role=role,
                        labels=labels,
                        status=status,
                    )
                )
            await session.commit()

    async def _record_validation_attempt(
        self,
        *,
        attempt_id: str,
        finding_id: str,
        audit_run_id: str,
        round_index: int,
        status: str,
        result: dict[str, Any],
        agent_run_id: str | None = None,
    ) -> None:
        async with SessionLocal() as session:
            existing = await session.scalar(select(ValidationAttempt).where(ValidationAttempt.attempt_id == attempt_id))
            if existing:
                existing.status = status
                existing.result = result
                existing.agent_run_id = agent_run_id or existing.agent_run_id
            else:
                session.add(
                    ValidationAttempt(
                        attempt_id=attempt_id,
                        finding_id=finding_id,
                        audit_run_id=audit_run_id,
                        agent_run_id=agent_run_id,
                        round_index=round_index,
                        status=status,
                        result=result,
                    )
                )
            await session.commit()

    async def _record_validation_evidence(
        self,
        *,
        finding_id: str,
        audit_run_id: str,
        kind: str,
        summary: str,
        payload: dict[str, Any],
    ) -> None:
        async with SessionLocal() as session:
            session.add(
                Evidence(
                    evidence_id=str(uuid.uuid4()),
                    finding_id=finding_id,
                    audit_run_id=audit_run_id,
                    kind=kind,
                    summary=summary,
                    payload=payload,
                )
            )
            await session.commit()

    async def _mark_findings_status(self, finding_ids: list[str], status: str) -> None:
        if not finding_ids:
            return
        async with SessionLocal() as session:
            rows = (await session.execute(select(Finding).where(Finding.finding_id.in_(finding_ids)))).scalars()
            for row in rows:
                row.status = status
            await session.commit()

    async def _record_agent_event(self, agent_run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        async with SessionLocal() as session:
            session.add(AgentRunEvent(agent_run_id=agent_run_id, event_type=event_type, payload=payload))
            await session.commit()

    async def _record_audit_run(
        self,
        *,
        audit_run_id: str,
        project_id: str,
        validator_rounds: int,
        max_parallel_validators: int,
        allow_external_network: bool,
        retain_runtime_on_failure: bool,
        config: dict[str, Any],
    ) -> None:
        async with SessionLocal() as session:
            existing = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
            if existing:
                existing.project_id = project_id
                existing.validator_rounds = validator_rounds
                existing.max_parallel_validators = max_parallel_validators
                existing.allow_external_network = allow_external_network
                existing.retain_runtime_on_failure = retain_runtime_on_failure
                existing.config = {**(existing.config or {}), **config}
            else:
                session.add(
                    AuditRun(
                        audit_run_id=audit_run_id,
                        project_id=project_id,
                        status="running",
                        validator_rounds=validator_rounds,
                        max_parallel_validators=max_parallel_validators,
                        allow_external_network=allow_external_network,
                        retain_runtime_on_failure=retain_runtime_on_failure,
                        config=config,
                    )
                )
            await session.commit()

    async def _record_agent_run(
        self,
        *,
        agent_run_id: str,
        audit_run_id: str,
        project_id: str,
        agent_name: str,
        template_name: str,
        protocol_kind: str,
        status: str,
        input_summary: dict[str, Any] | None = None,
        output_summary: dict[str, Any] | None = None,
        error: str | None = None,
        artifact_path: str | None = None,
    ) -> None:
        async with SessionLocal() as session:
            existing = await session.scalar(select(AgentRun).where(AgentRun.agent_run_id == agent_run_id))
            if existing:
                existing.status = status
                existing.output_summary = output_summary or existing.output_summary
                existing.error = error
                if artifact_path:
                    existing.artifact_path = artifact_path
            else:
                session.add(
                    AgentRun(
                        agent_run_id=agent_run_id,
                        audit_run_id=audit_run_id,
                        project_id=project_id,
                        agent_name=agent_name,
                        template_name=template_name,
                        protocol_kind=protocol_kind,
                        status=status,
                        input_summary=input_summary or {},
                        output_summary=output_summary or {},
                        artifact_path=artifact_path,
                        error=error,
                    )
                )
            await session.commit()

    async def _record_network(self, audit_run_id: str, name: str, status: str) -> None:
        async with SessionLocal() as session:
            existing = await session.scalar(select(RuntimeNetwork).where(RuntimeNetwork.name == name))
            if existing:
                existing.status = status
            else:
                session.add(RuntimeNetwork(audit_run_id=audit_run_id, name=name, status=status))
            await session.commit()

    async def _require_managed_run_network(self, *, network_name: str, audit_run_id: str) -> dict[str, Any]:
        network = await self.docker.network_exists(network_name)
        if not network:
            raise RuntimeError(f"sandbox network does not exist: {network_name}")
        labels = network.get("Labels") or {}
        if labels.get("dieaudit.managed") != "true":
            raise RuntimeError(f"sandbox network is not managed by DieAudit: {network_name}")
        if labels.get("dieaudit.audit_run_id") != audit_run_id:
            raise RuntimeError(f"sandbox network belongs to a different audit run: {network_name}")
        role = labels.get("dieaudit.role")
        if role not in {"runtime", "sandbox", "poc"}:
            raise RuntimeError(f"sandbox network has unsupported role label: {role or 'missing'}")
        return network

    async def _ensure_managed_run_network(
        self,
        *,
        network_name: str,
        audit_run_id: str,
        project_id: str,
        role: str,
        allow_external_network: bool,
        labels: dict[str, str],
    ) -> tuple[dict[str, Any], bool]:
        existing = await self.docker.network_exists(network_name)
        if existing:
            network = await self._require_managed_run_network(network_name=network_name, audit_run_id=audit_run_id)
            existing_labels = network.get("Labels") or {}
            if existing_labels.get("dieaudit.project_id") != project_id:
                raise RuntimeError(f"sandbox network belongs to a different project: {network_name}")
            if existing_labels.get("dieaudit.role") != role:
                raise RuntimeError(f"sandbox network has unsupported role label: {existing_labels.get('dieaudit.role') or 'missing'}")
            internal = bool(network.get("Internal"))
            if internal == allow_external_network:
                mode = "external" if allow_external_network else "internal"
                raise RuntimeError(f"sandbox network already exists with incompatible {mode} network policy: {network_name}")
            await self._record_network(audit_run_id, network_name, "reused")
            return network, False
        created = await self.docker.create_network(network_name, internal=not allow_external_network, labels=labels)
        await self._record_network(audit_run_id, network_name, "created")
        return created, True

    async def _mark_network_cleaned(self, audit_run_id: str, name: str) -> None:
        async with SessionLocal() as session:
            network = await session.scalar(
                select(RuntimeNetwork).where(
                    RuntimeNetwork.audit_run_id == audit_run_id,
                    RuntimeNetwork.name == name,
                )
            )
            if network:
                network.status = "cleaned"
            await session.commit()

    async def _mounts(
        self,
        workspace_host_path: str | None,
        template: dict[str, Any],
        *,
        artifact_host_path: Path | None = None,
    ) -> list[dict[str, Any]]:
        mounts: list[dict[str, Any]] = []
        if workspace_host_path:
            target = template.get("workspace_mount", {}).get("target", "/workspace")
            read_only = template.get("workspace_mount", {}).get("read_only", True)
            mounts.append(self._bind_mount(await self._host_path_for(Path(workspace_host_path)), target, read_only=read_only))
        artifact_mount = template.get("artifact_mount")
        if artifact_mount and artifact_host_path:
            target = artifact_mount.get("target", "/artifacts")
            mounts.append(
                self._bind_mount(
                    await self._host_path_for(artifact_host_path),
                    target,
                    read_only=artifact_mount.get("read_only", False),
                )
            )
        for mount in template.get("mounts", []):
            source = await self._host_path_for(Path(mount["source"]))
            target = mount["target"]
            mounts.append(self._bind_mount(source, target, read_only=mount.get("read_only", True)))
        return mounts

    async def _host_path_for(self, path: Path) -> str:
        requested = PurePosixPath(str(path).replace("\\", "/"))
        for mount in await self._current_gateway_mounts():
            if mount.get("Type") != "bind":
                continue
            destination = PurePosixPath(str(mount.get("Destination", "")).replace("\\", "/"))
            try:
                relative = requested.relative_to(destination)
            except ValueError:
                continue

            source = str(mount["Source"])
            if "\\" in source or (len(source) > 1 and source[1] == ":"):
                return ntpath.join(source, *relative.parts)
            return posixpath.join(source, *relative.parts)
        return str(path.resolve())

    async def _current_gateway_mounts(self) -> list[dict[str, Any]]:
        if self._gateway_mounts is None:
            info = await self.docker.inspect_container(self.settings.agent_gateway_container_name)
            self._gateway_mounts = info.get("Mounts", [])
        return self._gateway_mounts

    def _agent_artifact_dir(self, audit_run_id: str, agent_run_id: str) -> Path:
        return self.settings.artifact_root / "agent-runs" / audit_run_id / agent_run_id

    @staticmethod
    def _container_run_to_dict(row: ContainerRun, live: dict[str, Any] | None = None) -> dict[str, Any]:
        labels = row.labels or {}
        names = live.get("Names") if live else None
        if not names and row.container_name:
            names = [row.container_name if row.container_name.startswith("/") else f"/{row.container_name}"]
        state = live.get("State") if live else row.status
        status = live.get("Status") if live else row.status
        return {
            "Id": row.container_id,
            "Image": live.get("Image") if live else row.image,
            "Names": names or [],
            "State": state,
            "Status": status,
            "Labels": live.get("Labels") if live else labels,
            "container_id": row.container_id,
            "container_name": row.container_name,
            "agent_run_id": row.agent_run_id,
            "role": row.role,
            "db_status": row.status,
            "exit_code": row.exit_code,
            "log_artifact": row.log_artifact,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

    @staticmethod
    def _empty_managed_run(audit_run_id: str) -> dict[str, Any]:
        return {
            "audit_run_id": audit_run_id,
            "expired": False,
            "containers": [],
            "networks": [],
        }

    @classmethod
    def _managed_item_summary(cls, item: dict[str, Any], labels: dict[str, str], now: datetime) -> dict[str, Any]:
        ttl = labels.get("dieaudit.ttl")
        expires_at = cls._parse_ttl(ttl)
        item_id = item.get("Id") or item.get("ID") or item.get("Name")
        return {
            "id": item_id,
            "name": item.get("Name") or (item.get("Names") or [None])[0],
            "role": labels.get("dieaudit.role"),
            "ttl": ttl,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "expired": bool(expires_at and expires_at <= now),
            "state": item.get("State"),
            "status": item.get("Status"),
        }

    @staticmethod
    def _parse_ttl(value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _sandbox_warnings(
        *,
        configured_gvisor: bool,
        allow_runc_sandbox: bool,
        gvisor_available: bool,
        requested_runtime: str,
        requested_runtime_available: bool,
    ) -> list[str]:
        warnings: list[str] = []
        if configured_gvisor and not gvisor_available:
            warnings.append("ENABLE_GVISOR=true but Docker runtime 'runsc' is not installed.")
        if not requested_runtime_available:
            warnings.append(f"Docker runtime '{requested_runtime}' is not available on this host.")
        if requested_runtime == "runc" and allow_runc_sandbox:
            warnings.append("Sandbox is using Docker runc container isolation.")
        elif requested_runtime == "runc":
            warnings.append("Sandbox execution is disabled with runc until ALLOW_RUNC_SANDBOX=true.")
        return warnings

    async def _require_sandbox_execution(self, *, allow_weak_isolation: bool) -> dict[str, Any]:
        capabilities = await self.sandbox_capabilities()
        if capabilities.get("sandbox_execution_available"):
            return capabilities
        requested_runtime = str(capabilities.get("requested_runtime") or self.settings.default_sandbox_runtime)
        if requested_runtime == "runc" and allow_weak_isolation and capabilities.get("requested_runtime_available"):
            allowed = dict(capabilities)
            allowed["ok"] = True
            allowed["sandbox_execution_available"] = True
            allowed["policy_ok"] = False
            allowed["docker_isolation_override"] = True
            allowed["warnings"] = [
                *list(allowed.get("warnings") or []),
                "This run explicitly allowed Docker runc container isolation.",
            ]
            return allowed
        raise RuntimeError(capabilities.get("reason") or "sandbox execution is not available")

    @staticmethod
    def _safe_artifact_name(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip("/\\"))
        return cleaned.strip("-")[:96] or "container"

    @staticmethod
    def _parse_probe_logs(logs: str) -> dict[str, Any]:
        for line in reversed([item.strip() for item in logs.splitlines() if item.strip()]):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return {"error": "probe did not emit JSON", "logs_tail": logs[-1000:]}

    @staticmethod
    def _bind_mount(source: str, target: str, *, read_only: bool) -> dict[str, Any]:
        return {"Type": "bind", "Source": source, "Target": target, "ReadOnly": read_only}

    @staticmethod
    def _inject_no_proxy(env: dict[str, Any], mcp_servers: dict[str, dict[str, str]]) -> None:
        internal_hosts = ["localhost", "127.0.0.1", "agent-gateway", "host.docker.internal"]
        for server in mcp_servers.values():
            hostname = urlparse(server["url"]).hostname
            if hostname:
                internal_hosts.append(hostname)
        RuntimeOrchestrator._inject_internal_no_proxy(env, internal_hosts)

    @staticmethod
    def _inject_internal_no_proxy(env: dict[str, Any], internal_hosts: list[str]) -> None:
        existing = str(env.get("NO_PROXY") or env.get("no_proxy") or "")
        merged = [item for item in existing.split(",") if item]
        for host in internal_hosts:
            if host not in merged:
                merged.append(host)
        env["NO_PROXY"] = ",".join(merged)
        env["no_proxy"] = env["NO_PROXY"]

    def _runtime_container_name(self, *, audit_run_id: str, role: str, template_name: str, run_id: str) -> str:
        prefix = self._dns_label_part(str(getattr(self.settings, "dynamic_container_prefix", "dieaudit")), max_length=10) or "dieaudit"
        role_part = self._dns_label_part(role, max_length=8) or "run"
        template_part = self._dns_label_part(template_name, max_length=18) or "item"
        run_part = self._dns_label_part(run_id.replace("-", ""), max_length=12) or uuid.uuid4().hex[:12]
        audit_hash = uuid.uuid5(uuid.NAMESPACE_URL, str(audit_run_id)).hex[:8]
        return f"{prefix}-{audit_hash}-{role_part}-{template_part}-{run_part}"[:63].rstrip("-")

    async def _connect_runtime_controllers(self, network_name: str) -> None:
        for container_name, alias in self._runtime_controller_targets():
            await self.docker.connect_network(network_name, container_name, aliases=[alias])

    async def _disconnect_runtime_controllers(self, network_name: str) -> None:
        for container_name, _alias in self._runtime_controller_targets():
            await self.docker.disconnect_network(network_name, container_name)
        for container_name in self._known_runtime_controller_container_names():
            await self.docker.disconnect_network(network_name, container_name)

    async def _ensure_agent_run_network(
        self,
        network_name: str,
        *,
        allow_external_network: bool,
        labels: dict[str, str],
    ) -> dict[str, Any]:
        existing = await self.docker.network_exists(network_name)
        if existing:
            internal = bool(existing.get("Internal"))
            if internal != allow_external_network:
                return existing
            await self._disconnect_runtime_controllers(network_name)
            await self.docker.remove_network(network_name)
        return await self.docker.create_network(network_name, internal=not allow_external_network, labels=labels)

    def _runtime_controller_targets(self) -> list[tuple[str, str]]:
        targets = [(self.settings.agent_gateway_container_name, "agent-gateway")]
        current = self._current_runtime_controller_container_name()
        if current and current != self.settings.agent_gateway_container_name:
            targets.append((current, self._dns_label_part(str(self.settings.service_name), max_length=32) or "runtime-controller"))
        deduped: list[tuple[str, str]] = []
        seen: set[str] = set()
        for container_name, alias in targets:
            if container_name and container_name not in seen:
                deduped.append((container_name, alias))
                seen.add(container_name)
        return deduped

    def _current_runtime_controller_container_name(self) -> str | None:
        configured = str(getattr(self.settings, "runtime_controller_container_name", "") or "").strip()
        if configured:
            return configured
        service_name = str(getattr(self.settings, "service_name", "") or "").strip()
        if not service_name:
            return None
        return f"{getattr(self.settings, 'dynamic_container_prefix', 'dieaudit')}-{service_name}"

    def _known_runtime_controller_container_names(self) -> list[str]:
        prefix = getattr(self.settings, "dynamic_container_prefix", "dieaudit")
        names = [
            self.settings.agent_gateway_container_name,
            f"{prefix}-workflow-worker",
            f"{prefix}-sandbox-runner",
        ]
        current = self._current_runtime_controller_container_name()
        if current:
            names.append(current)
        return list(dict.fromkeys(name for name in names if name))

    @staticmethod
    def _dns_label_part(value: str, *, max_length: int) -> str:
        text = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
        text = re.sub(r"-+", "-", text)
        return text[:max_length].strip("-")

    @staticmethod
    def _mcp_base_url(container: dict[str, Any], template: dict[str, Any]) -> str:
        host = container.get("host") or container.get("name")
        return f"http://{host}:{template.get('port', 8001)}"

    async def _wait_for_mcp_http(self, host: str, template: dict[str, Any], *, timeout_seconds: int = 45) -> dict[str, Any]:
        health_path = str(template.get("healthcheck_path") or "/health")
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        url = f"http://{host}:{template.get('port', 8001)}{health_path}"
        last_error = ""
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            while asyncio.get_running_loop().time() < deadline:
                try:
                    response = await client.get(url)
                    if response.status_code < 400:
                        return {"url": url, "status_code": response.status_code}
                    last_error = f"HTTP {response.status_code}: {response.text[:500]}"
                except Exception as exc:
                    last_error = str(exc)
                await asyncio.sleep(1)
        raise RuntimeError(f"MCP {template.get('name', host)} not healthy at {url}: {last_error}")

    @staticmethod
    def _is_opencode_agent(template: dict[str, Any]) -> bool:
        protocol = template.get("protocol", {})
        return protocol.get("kind") == "agent-client-protocol" and protocol.get("runtime") == "opencode"

    def _resource_host_config(self, resources: dict[str, Any] | None) -> dict[str, Any]:
        resources = resources or {}
        host_config: dict[str, Any] = {}
        memory = self._parse_memory_bytes(resources.get("memory", self.settings.default_container_memory))
        if memory:
            host_config["Memory"] = memory
        nano_cpus = resources.get("nano_cpus")
        if nano_cpus is None:
            cpus = resources.get("cpus", self.settings.default_container_cpus)
            try:
                nano_cpus = int(float(cpus) * 1_000_000_000)
            except (TypeError, ValueError):
                nano_cpus = None
        if nano_cpus:
            host_config["NanoCpus"] = int(nano_cpus)
        pids_limit = resources.get("pids_limit", self.settings.default_container_pids_limit)
        if pids_limit:
            host_config["PidsLimit"] = int(pids_limit)
        tmpfs = self._parse_tmpfs(resources.get("tmpfs", self.settings.default_container_tmpfs))
        if tmpfs:
            host_config["Tmpfs"] = tmpfs
        return host_config

    @staticmethod
    def _parse_memory_bytes(value: Any) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, int):
            return value if value > 0 else None
        text = str(value).strip().lower()
        match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmgt]?i?b?|)", text)
        if not match:
            return None
        number = float(match.group(1))
        suffix = match.group(2)
        multipliers = {
            "": 1,
            "b": 1,
            "k": 1024,
            "kb": 1024,
            "ki": 1024,
            "kib": 1024,
            "m": 1024**2,
            "mb": 1024**2,
            "mi": 1024**2,
            "mib": 1024**2,
            "g": 1024**3,
            "gb": 1024**3,
            "gi": 1024**3,
            "gib": 1024**3,
            "t": 1024**4,
            "tb": 1024**4,
            "ti": 1024**4,
            "tib": 1024**4,
        }
        return int(number * multipliers.get(suffix, 1))

    @staticmethod
    def _parse_tmpfs(value: Any) -> dict[str, str] | None:
        if not value:
            return None
        if isinstance(value, dict):
            return {str(target): str(options) for target, options in value.items() if target}
        entries = value if isinstance(value, list) else [value]
        tmpfs: dict[str, str] = {}
        for entry in entries:
            text = str(entry).strip()
            if not text:
                continue
            target, _, options = text.partition(":")
            tmpfs[target] = options or "rw,nosuid,size=64m"
        return tmpfs or None

    def _container_payload(
        self,
        *,
        image: str,
        command: list[str] | str | None,
        env: dict[str, Any],
        labels: dict[str, str],
        network_name: str,
        aliases: list[str],
        mounts: list[dict[str, Any]],
        read_only: bool,
        healthcheck: dict[str, Any] | None,
        runtime: str | None = None,
        resources: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        env_list = [f"{key}={value}" for key, value in env.items()]
        host_config = {
            "NetworkMode": network_name,
            "Mounts": mounts,
            "ExtraHosts": ["host.docker.internal:host-gateway"],
            "ReadonlyRootfs": read_only,
            "AutoRemove": False,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
        }
        host_config.update(self._resource_host_config(resources))
        payload: dict[str, Any] = {
            "Image": image,
            "Env": env_list,
            "Labels": labels,
            "HostConfig": host_config,
            "NetworkingConfig": {"EndpointsConfig": {network_name: {"Aliases": aliases}}},
        }
        if command:
            payload["Cmd"] = command if isinstance(command, list) else [command]
        if healthcheck:
            payload["Healthcheck"] = healthcheck
        if runtime:
            payload["HostConfig"]["Runtime"] = runtime
        return payload

    @staticmethod
    def _labels(audit_run_id: str, project_id: str, *, role: str, ttl: str) -> dict[str, str]:
        return {
            "dieaudit.managed": "true",
            "dieaudit.audit_run_id": audit_run_id,
            "dieaudit.project_id": project_id,
            "dieaudit.role": role,
            "dieaudit.ttl": ttl,
        }

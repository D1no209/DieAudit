import json
import ntpath
import posixpath
import re
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from app.domain.models import AgentRun, AgentRunEvent, AuditRun, ContainerRun, Evidence, Finding, RuntimeNetwork, ValidationAttempt
from app.integrations.docker import DockerClient
from app.integrations.protocols import OpenCodeAcpClient
from app.repositories import SessionLocal
from app.runtime.opencode_package import OpenCodeRuntimePackageBuilder
from app.services.agent_output import AgentOutputIngestor
from app.services.templates import TemplateStore
from app.settings import Settings


def utc_ttl(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


class RuntimeOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.docker = DockerClient(settings.docker_host)
        self.agent_templates = TemplateStore(settings.config_root, "agent-templates")
        self.mcp_templates = TemplateStore(settings.config_root, "mcp-templates")
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

        await self.docker.create_network(network_name, internal=not allow_external_network, labels=labels)
        await self.docker.connect_network(network_name, self.settings.agent_gateway_container_name, aliases=["agent-gateway"])
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
                        "url": f"http://{mcp_container['name']}:{mcp.get('port', 8001)}{endpoint}",
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
            await self.docker.disconnect_network(network_name, self.settings.agent_gateway_container_name)
            await self.docker.remove_network(network_name)
            await self._mark_network_cleaned(audit_run_id, network_name)
            removed_networks.append(network_name)
        return {"audit_run_id": audit_run_id, "removed_containers": removed, "removed_networks": removed_networks}

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
        await self.docker.connect_network(network_name, self.settings.agent_gateway_container_name, aliases=["agent-gateway"])
        await self._record_network(audit_run_id, network_name, "created")
        template = self.mcp_templates.get(mcp_name)
        container: dict[str, Any] | None = None
        container_cleaned = False
        try:
            container = await self._start_mcp(
                audit_run_id=audit_run_id,
                project_id=project_id,
                agent_run_id=f"tool-{tool_run_id}",
                network_name=network_name,
                workspace_host_path=workspace_host_path,
                template=template,
            )
            url = f"http://{container['name']}:{template.get('port', 8001)}{tool_path}"
            async with httpx.AsyncClient(timeout=template.get("tool_timeout_seconds", 900), trust_env=False) as client:
                response = await client.post(url, json=payload or {})
            if response.status_code >= 400:
                raise RuntimeError(f"{mcp_name} {tool_path} failed: {response.status_code} {response.text}")
            result = response.json()
            return {"ok": True, "mcp": container, "result": result}
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
        finally:
            if not retain_runtime_on_failure and container and not container_cleaned:
                await self._capture_and_remove_container(
                    audit_run_id=audit_run_id,
                    container_id=container["id"],
                    container_name=container.get("name"),
                )
                container_cleaned = True
            if dedicated_network and not retain_runtime_on_failure:
                await self.docker.disconnect_network(network_name, self.settings.agent_gateway_container_name)
                await self.docker.remove_network(network_name)
                await self._mark_network_cleaned(audit_run_id, network_name)

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

        semaphore = asyncio.Semaphore(max_parallel_validators)

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
            async with semaphore:
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
                return result

        scheduled: list[asyncio.Task] = []
        await self._mark_findings_status([str(finding.get("finding_id")) for finding in findings if finding.get("finding_id")], "validating")
        for finding in findings:
            for round_index in range(1, validator_rounds + 1):
                scheduled.append(asyncio.create_task(run_validator(finding, round_index)))

        async def drain(tasks: list[asyncio.Task]) -> None:
            for task in asyncio.as_completed(tasks):
                try:
                    await task
                except Exception:
                    pass

        if wait_for_completion:
            await drain(scheduled)
        else:
            asyncio.create_task(drain(scheduled))
        return {
            "audit_run_id": audit_run_id,
            "project_id": project_id,
            "status": "accepted",
            "scheduled": len(scheduled),
            "validator_rounds": validator_rounds,
            "max_parallel_validators": max_parallel_validators,
            "validator_agent_name": validator_agent_name,
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
        name = f"{self.settings.dynamic_container_prefix}-{audit_run_id}-{template['name']}-{agent_run_id[:8]}"
        labels = self._labels(audit_run_id, project_id, role="mcp", ttl=utc_ttl())
        labels["dieaudit.mcp"] = template["name"]
        labels["dieaudit.agent_run_id"] = agent_run_id

        mcp_artifact_path = self.settings.artifact_root / "mcp-runs" / audit_run_id / agent_run_id / template["name"]
        mcp_artifact_path.mkdir(parents=True, exist_ok=True)
        mounts = await self._mounts(workspace_host_path, template, artifact_host_path=mcp_artifact_path)
        payload = self._container_payload(
            image=image,
            command=template.get("command"),
            env=template.get("env", {}),
            labels=labels,
            network_name=network_name,
            aliases=[name, template["name"]],
            mounts=mounts,
            read_only=template.get("read_only", True),
            healthcheck=template.get("healthcheck"),
        )
        created = await self.docker.create_container(name, payload)
        await self.docker.start_container(created["Id"])
        await self._record_container(audit_run_id, project_id, agent_run_id, created["Id"], name, image, "mcp", labels, "starting")
        await self.docker.wait_for_healthy(created["Id"], timeout_seconds=template.get("health_timeout_seconds", 45))
        await self._record_container(audit_run_id, project_id, agent_run_id, created["Id"], name, image, "mcp", labels, "running")
        return {"id": created["Id"], "name": name, "image": image, "role": "mcp", "template": template["name"]}

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
        name = f"{self.settings.dynamic_container_prefix}-{audit_run_id}-{template['name']}-{agent_run_id[:8]}"
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
        wait_result = await self.docker.wait_container(container_id)
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
        if result_file.exists():
            try:
                payload.update(json.loads(result_file.read_text(encoding="utf-8")))
            except json.JSONDecodeError as exc:
                payload["error"] = f"invalid agent_result.json: {exc}"
        else:
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
    def _safe_artifact_name(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip("/\\"))
        return cleaned.strip("-")[:96] or "container"

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
        existing = str(env.get("NO_PROXY") or env.get("no_proxy") or "")
        merged = [item for item in existing.split(",") if item]
        for host in internal_hosts:
            if host not in merged:
                merged.append(host)
        env["NO_PROXY"] = ",".join(merged)
        env["no_proxy"] = env["NO_PROXY"]

    @staticmethod
    def _is_opencode_agent(template: dict[str, Any]) -> bool:
        protocol = template.get("protocol", {})
        return protocol.get("kind") == "agent-client-protocol" and protocol.get("runtime") == "opencode"

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
    ) -> dict[str, Any]:
        env_list = [f"{key}={value}" for key, value in env.items()]
        payload: dict[str, Any] = {
            "Image": image,
            "Env": env_list,
            "Labels": labels,
            "HostConfig": {
                "NetworkMode": network_name,
                "Mounts": mounts,
                "ExtraHosts": ["host.docker.internal:host-gateway"],
                "ReadonlyRootfs": read_only,
                "AutoRemove": False,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges:true"],
            },
            "NetworkingConfig": {"EndpointsConfig": {network_name: {"Aliases": aliases}}},
        }
        if command:
            payload["Cmd"] = command if isinstance(command, list) else [command]
        if healthcheck:
            payload["Healthcheck"] = healthcheck
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

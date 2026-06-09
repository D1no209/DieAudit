import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.domain.models import AgentRun, ContainerRun, RuntimeNetwork
from app.integrations.docker import DockerClient
from app.repositories import SessionLocal
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

    async def close(self) -> None:
        await self.docker.close()

    async def docker_health(self) -> dict[str, Any]:
        ping = await self.docker.ping()
        version = await self.docker.version()
        return {"ok": ping == "OK", "ping": ping, "version": version}

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
                    mcp_servers[mcp["name"]] = {
                        "transport": mcp.get("transport", "http"),
                        "url": f"http://{mcp_container['name']}:{mcp.get('port', 8001)}",
                    }

            agent_container = await self._start_agent(
                audit_run_id=audit_run_id,
                project_id=project_id,
                agent_run_id=run_id,
                network_name=network_name,
                workspace_host_path=workspace_host_path,
                template=agent,
                mcp_servers=mcp_servers,
                input_payload=input_payload or {},
            )
            await self._record_agent_run(
                agent_run_id=run_id,
                audit_run_id=audit_run_id,
                project_id=project_id,
                agent_name=agent_name,
                template_name=agent.get("name", agent_name),
                protocol_kind=protocol_kind,
                status="running",
                input_summary=input_payload or {},
                output_summary={"container_id": agent_container["id"], "mcp_servers": mcp_servers},
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
            await self.docker.remove_container(cid, force=True)

        network_name = f"{self.settings.dynamic_container_prefix}-run-{audit_run_id}"
        await self.docker.disconnect_network(network_name, self.settings.agent_gateway_container_name)
        await self.docker.remove_network(network_name)
        await self._mark_network_cleaned(audit_run_id, network_name)
        return {"audit_run_id": audit_run_id, "removed_containers": removed, "removed_network": network_name}

    async def containers(self, audit_run_id: str) -> list[dict[str, Any]]:
        return await self.docker.list_containers_by_run(audit_run_id)

    async def logs(self, container_id: str) -> str:
        return await self.docker.logs(container_id)

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

        binds = self._binds(workspace_host_path, template)
        payload = self._container_payload(
            image=image,
            command=template.get("command"),
            env=template.get("env", {}),
            labels=labels,
            network_name=network_name,
            aliases=[name, template["name"]],
            binds=binds,
            read_only=template.get("read_only", True),
            healthcheck=template.get("healthcheck"),
        )
        created = await self.docker.create_container(name, payload)
        await self.docker.start_container(created["Id"])
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
        binds = self._binds(workspace_host_path, template)
        payload = self._container_payload(
            image=image,
            command=template.get("command"),
            env=env,
            labels=labels,
            network_name=network_name,
            aliases=[name, template["name"]],
            binds=binds,
            read_only=template.get("read_only", True),
            healthcheck=template.get("healthcheck"),
        )
        created = await self.docker.create_container(name, payload)
        await self.docker.start_container(created["Id"])
        await self._record_container(audit_run_id, project_id, agent_run_id, created["Id"], name, image, "agent", labels, "running")
        return {"id": created["Id"], "name": name, "image": image, "role": "agent", "template": template["name"]}

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
    ) -> None:
        async with SessionLocal() as session:
            existing = await session.scalar(select(AgentRun).where(AgentRun.agent_run_id == agent_run_id))
            if existing:
                existing.status = status
                existing.output_summary = output_summary or existing.output_summary
                existing.error = error
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

    def _binds(self, workspace_host_path: str | None, template: dict[str, Any]) -> list[str]:
        binds: list[str] = []
        if workspace_host_path:
            target = template.get("workspace_mount", {}).get("target", "/workspace")
            mode = "ro" if template.get("workspace_mount", {}).get("read_only", True) else "rw"
            binds.append(f"{Path(workspace_host_path).resolve()}:{target}:{mode}")
        for mount in template.get("mounts", []):
            source = mount["source"]
            target = mount["target"]
            mode = "ro" if mount.get("read_only", True) else "rw"
            binds.append(f"{source}:{target}:{mode}")
        return binds

    def _container_payload(
        self,
        *,
        image: str,
        command: list[str] | str | None,
        env: dict[str, Any],
        labels: dict[str, str],
        network_name: str,
        aliases: list[str],
        binds: list[str],
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
                "Binds": binds,
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

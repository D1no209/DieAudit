from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.integrations.docker.client import DockerClient
from app.runtime.orchestrator import RuntimeOrchestrator


def _orchestrator() -> RuntimeOrchestrator:
    orchestrator = RuntimeOrchestrator.__new__(RuntimeOrchestrator)
    orchestrator.settings = SimpleNamespace(
        api_key_header="X-DieAudit-Api-Key",
        default_container_memory="512m",
        default_container_cpus=0.5,
        default_container_pids_limit=128,
        default_container_tmpfs="/tmp:rw,nosuid,size=64m",
    )
    return orchestrator


def test_runtime_container_payload_applies_security_and_resource_defaults() -> None:
    payload = _orchestrator()._container_payload(
        image="example:latest",
        command=["run"],
        env={"A": "1"},
        labels={"dieaudit.managed": "true"},
        network_name="dieaudit-run-1",
        aliases=["agent"],
        mounts=[],
        read_only=True,
        healthcheck=None,
    )

    host_config = payload["HostConfig"]
    assert host_config["ReadonlyRootfs"] is True
    assert host_config["CapDrop"] == ["ALL"]
    assert host_config["SecurityOpt"] == ["no-new-privileges:true"]
    assert host_config["Memory"] == 512 * 1024 * 1024
    assert host_config["NanoCpus"] == 500_000_000
    assert host_config["PidsLimit"] == 128
    assert host_config["Tmpfs"] == {"/tmp": "rw,nosuid,size=64m"}


def test_runtime_container_payload_allows_template_resource_overrides() -> None:
    payload = _orchestrator()._container_payload(
        image="example:latest",
        command=None,
        env={},
        labels={},
        network_name="dieaudit-run-1",
        aliases=[],
        mounts=[],
        read_only=True,
        healthcheck=None,
        runtime="runsc",
        resources={
            "memory": "1g",
            "cpus": 2,
            "pids_limit": 64,
            "tmpfs": ["/tmp:rw,noexec,nosuid,size=32m"],
        },
    )

    host_config = payload["HostConfig"]
    assert host_config["Runtime"] == "runsc"
    assert host_config["Memory"] == 1024 * 1024 * 1024
    assert host_config["NanoCpus"] == 2_000_000_000
    assert host_config["PidsLimit"] == 64
    assert host_config["Tmpfs"] == {"/tmp": "rw,noexec,nosuid,size=32m"}


def test_ephemeral_container_payload_is_hardened(monkeypatch) -> None:
    asyncio.run(_run_ephemeral_container_payload_test(monkeypatch))


def test_reused_sandbox_network_must_be_managed_current_run(monkeypatch) -> None:
    asyncio.run(_run_reused_sandbox_network_policy_test(monkeypatch))


def test_sandbox_network_creation_and_reuse_policy(monkeypatch) -> None:
    asyncio.run(_run_sandbox_network_creation_and_reuse_policy_test(monkeypatch))


def test_mcp_platform_api_env_uses_scoped_sidecar_key(monkeypatch) -> None:
    asyncio.run(_run_mcp_platform_api_env_test(monkeypatch))


def test_cleanup_deactivates_scoped_mcp_sidecar_keys(monkeypatch) -> None:
    asyncio.run(_run_cleanup_deactivates_scoped_mcp_sidecar_keys(monkeypatch))


async def _run_cleanup_deactivates_scoped_mcp_sidecar_keys(monkeypatch) -> None:
    import app.runtime.orchestrator as orchestrator_module

    orchestrator = _orchestrator()
    rows = [
        SimpleNamespace(
            key_id="mcp-current",
            status="active",
            deactivated_at=None,
            metadata_json={"kind": "mcp-sidecar", "audit_run_ids": ["run-1"]},
        ),
        SimpleNamespace(
            key_id="mcp-other-run",
            status="active",
            deactivated_at=None,
            metadata_json={"kind": "mcp-sidecar", "audit_run_ids": ["run-2"]},
        ),
        SimpleNamespace(
            key_id="user-project-key",
            status="active",
            deactivated_at=None,
            metadata_json={"project_ids": ["project-1"]},
        ),
    ]

    class FakeResult:
        def scalars(self):
            return rows

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, _statement):
            return FakeResult()

        async def commit(self):
            self.committed = True

    monkeypatch.setattr(orchestrator_module, "SessionLocal", lambda: FakeSession())

    deactivated = await orchestrator._deactivate_mcp_api_keys("run-1")

    assert deactivated == ["mcp-current"]
    assert rows[0].status == "inactive"
    assert rows[0].deactivated_at is not None
    assert rows[1].status == "active"
    assert rows[1].deactivated_at is None
    assert rows[2].status == "active"
    assert rows[2].deactivated_at is None


async def _run_mcp_platform_api_env_test(monkeypatch) -> None:
    import app.runtime.orchestrator as orchestrator_module

    orchestrator = _orchestrator()
    captured = {}

    async def fake_create_persisted_api_key(**kwargs):
        captured.update(kwargs)
        return {"api_key": "dak_scoped_mcp_key", "record": {"key_id": "key-1"}}

    monkeypatch.setattr(orchestrator_module, "create_persisted_api_key", fake_create_persisted_api_key)

    env = await orchestrator._mcp_env(
        template={
            "name": "kb-mcp",
            "env": {"MCP_NAME": "kb-mcp"},
            "permissions": {"platform_api": "knowledge"},
        },
        audit_run_id="run-1",
        project_id="project-1",
        agent_run_id="agent-1234567890",
    )

    assert env["DIEAUDIT_API_KEY"] == "dak_scoped_mcp_key"
    assert env["API_KEY_HEADER"] == "X-DieAudit-Api-Key"
    assert env["AUDIT_RUN_ID"] == "run-1"
    assert env["PROJECT_ID"] == "project-1"
    assert captured["scopes"] == ["read"]
    assert captured["default_scope"] == "read"
    assert captured["metadata"]["kind"] == "mcp-sidecar"
    assert captured["metadata"]["mcp"] == "kb-mcp"
    assert captured["metadata"]["project_ids"] == ["project-1"]
    assert captured["metadata"]["audit_run_ids"] == ["run-1"]
    assert captured["metadata"]["agent_run_id"] == "agent-1234567890"


async def _run_sandbox_network_creation_and_reuse_policy_test(monkeypatch) -> None:
    orchestrator = _orchestrator()
    events = []
    networks = {
        "dieaudit-run-1-sandbox": {
            "Name": "dieaudit-run-1-sandbox",
            "Internal": True,
            "Labels": {
                "dieaudit.managed": "true",
                "dieaudit.audit_run_id": "run-1",
                "dieaudit.project_id": "project-1",
                "dieaudit.role": "sandbox",
            },
        },
        "dieaudit-run-1-external": {
            "Name": "dieaudit-run-1-external",
            "Internal": False,
            "Labels": {
                "dieaudit.managed": "true",
                "dieaudit.audit_run_id": "run-1",
                "dieaudit.project_id": "project-1",
                "dieaudit.role": "sandbox",
            },
        },
        "dieaudit-run-1-other-project": {
            "Name": "dieaudit-run-1-other-project",
            "Internal": True,
            "Labels": {
                "dieaudit.managed": "true",
                "dieaudit.audit_run_id": "run-1",
                "dieaudit.project_id": "project-2",
                "dieaudit.role": "sandbox",
            },
        },
    }

    async def fake_network_exists(name):
        return networks.get(name)

    async def fake_create_network(name, *, internal=True, labels=None):
        created = {"Name": name, "Internal": internal, "Labels": labels or {}}
        networks[name] = created
        events.append(("create_network", name, internal))
        return created

    async def fake_record_network(audit_run_id, name, status):
        events.append(("record_network", audit_run_id, name, status))

    orchestrator.docker = SimpleNamespace(network_exists=fake_network_exists, create_network=fake_create_network)
    monkeypatch.setattr(orchestrator, "_record_network", fake_record_network)

    created, created_now = await orchestrator._ensure_managed_run_network(
        network_name="dieaudit-run-1-new",
        audit_run_id="run-1",
        project_id="project-1",
        role="sandbox",
        allow_external_network=False,
        labels={
            "dieaudit.managed": "true",
            "dieaudit.audit_run_id": "run-1",
            "dieaudit.project_id": "project-1",
            "dieaudit.role": "sandbox",
        },
    )
    assert created["Name"] == "dieaudit-run-1-new"
    assert created["Internal"] is True
    assert created_now is True
    assert ("record_network", "run-1", "dieaudit-run-1-new", "created") in events

    reused, created_now = await orchestrator._ensure_managed_run_network(
        network_name="dieaudit-run-1-sandbox",
        audit_run_id="run-1",
        project_id="project-1",
        role="sandbox",
        allow_external_network=False,
        labels={},
    )
    assert reused["Name"] == "dieaudit-run-1-sandbox"
    assert created_now is False
    assert ("record_network", "run-1", "dieaudit-run-1-sandbox", "reused") in events

    rejected_cases = [
        ("dieaudit-run-1-sandbox", True),
        ("dieaudit-run-1-external", False),
        ("dieaudit-run-1-other-project", False),
    ]
    for network_name, allow_external_network in rejected_cases:
        try:
            await orchestrator._ensure_managed_run_network(
                network_name=network_name,
                audit_run_id="run-1",
                project_id="project-1",
                role="sandbox",
                allow_external_network=allow_external_network,
                labels={},
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"network should have been rejected: {network_name}")


async def _run_reused_sandbox_network_policy_test(monkeypatch) -> None:
    orchestrator = _orchestrator()
    networks = {
        "dieaudit-run-1-sandbox": {
            "Name": "dieaudit-run-1-sandbox",
            "Labels": {
                "dieaudit.managed": "true",
                "dieaudit.audit_run_id": "run-1",
                "dieaudit.role": "sandbox",
            },
        },
        "dieaudit-run-2-sandbox": {
            "Name": "dieaudit-run-2-sandbox",
            "Labels": {
                "dieaudit.managed": "true",
                "dieaudit.audit_run_id": "run-2",
                "dieaudit.role": "sandbox",
            },
        },
        "external": {"Name": "external", "Labels": {}},
        "dieaudit-run-1-unknown": {
            "Name": "dieaudit-run-1-unknown",
            "Labels": {
                "dieaudit.managed": "true",
                "dieaudit.audit_run_id": "run-1",
            },
        },
    }

    async def fake_network_exists(name):
        return networks.get(name)

    orchestrator.docker = SimpleNamespace(network_exists=fake_network_exists)

    allowed = await orchestrator._require_managed_run_network(network_name="dieaudit-run-1-sandbox", audit_run_id="run-1")
    assert allowed["Name"] == "dieaudit-run-1-sandbox"

    for network_name in ("external", "dieaudit-run-2-sandbox", "dieaudit-run-1-unknown", "missing"):
        try:
            await orchestrator._require_managed_run_network(network_name=network_name, audit_run_id="run-1")
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"network should have been rejected: {network_name}")


async def _run_ephemeral_container_payload_test(monkeypatch) -> None:
    client = DockerClient("http://docker.example")
    captured_payload = {}

    async def fake_create_container(name, payload):
        captured_payload.update(payload)
        return {"Id": "container-1"}

    async def fake_start_container(_container_id):
        return None

    async def fake_wait_container(_container_id):
        return {"StatusCode": 0}

    async def fake_logs(_container_id, **_kwargs):
        return "{}"

    async def fake_remove_container(_container_id, **_kwargs):
        return None

    monkeypatch.setattr(client, "create_container", fake_create_container)
    monkeypatch.setattr(client, "start_container", fake_start_container)
    monkeypatch.setattr(client, "wait_container", fake_wait_container)
    monkeypatch.setattr(client, "logs", fake_logs)
    monkeypatch.setattr(client, "remove_container", fake_remove_container)

    try:
        await client.run_ephemeral_container(
            name="probe",
            image="example:latest",
            command=["python", "-V"],
        )
    finally:
        await client.close()

    host_config = captured_payload["HostConfig"]
    assert host_config["NetworkMode"] == "none"
    assert host_config["ReadonlyRootfs"] is True
    assert host_config["CapDrop"] == ["ALL"]
    assert host_config["SecurityOpt"] == ["no-new-privileges:true"]
    assert host_config["Memory"] == 256 * 1024 * 1024
    assert host_config["NanoCpus"] == 500_000_000
    assert host_config["PidsLimit"] == 128
    assert host_config["Tmpfs"] == {"/tmp": "rw,nosuid,size=64m"}

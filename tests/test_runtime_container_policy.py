from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.integrations.docker.client import DockerClient
from app.runtime.orchestrator import RuntimeOrchestrator


def _orchestrator() -> RuntimeOrchestrator:
    orchestrator = RuntimeOrchestrator.__new__(RuntimeOrchestrator)
    orchestrator.settings = SimpleNamespace(
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

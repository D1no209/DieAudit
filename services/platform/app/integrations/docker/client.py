import asyncio
import json
import time
from typing import Any
from urllib.parse import quote

import httpx


class DockerApiError(RuntimeError):
    pass


class DockerClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.replace("tcp://", "http://").rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=60, trust_env=False)

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self.client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise DockerApiError(f"{method} {path} failed: {response.status_code} {response.text}")
        if not response.content:
            return None
        try:
            return response.json()
        except json.JSONDecodeError:
            return response.text

    async def ping(self) -> str:
        return await self.request("GET", "/_ping")

    async def version(self) -> dict[str, Any]:
        return await self.request("GET", "/version")

    async def info(self) -> dict[str, Any]:
        return await self.request("GET", "/info")

    async def pull_image(self, image: str) -> None:
        if await self.image_exists(image):
            return
        from_image, tag = image, None
        if ":" in image and "/" not in image.rsplit(":", 1)[-1]:
            from_image, tag = image.rsplit(":", 1)
        params: dict[str, str] = {"fromImage": from_image}
        if tag:
            params["tag"] = tag
        async with self.client.stream("POST", "/images/create", params=params, timeout=None) as response:
            if response.status_code >= 400:
                text = await response.aread()
                raise DockerApiError(f"pull {image} failed: {response.status_code} {text.decode(errors='replace')}")
            async for _ in response.aiter_lines():
                pass

    async def image_exists(self, image: str) -> bool:
        encoded = quote(image, safe="")
        response = await self.client.get(f"/images/{encoded}/json")
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        if response.status_code >= 400:
            raise DockerApiError(f"inspect image {image} failed: {response.status_code} {response.text}")
        return True

    async def create_network(self, name: str, *, internal: bool = True, labels: dict[str, str] | None = None) -> dict[str, Any]:
        existing = await self.network_exists(name)
        if existing:
            return existing
        payload = {
            "Name": name,
            "Driver": "bridge",
            "Internal": internal,
            "Labels": labels or {},
            "CheckDuplicate": True,
        }
        return await self.request("POST", "/networks/create", json=payload)

    async def network_exists(self, name: str) -> dict[str, Any] | None:
        response = await self.client.get(f"/networks/{name}")
        if response.status_code == 200:
            return response.json()
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise DockerApiError(f"inspect network {name} failed: {response.status_code} {response.text}")
        return response.json()

    async def connect_network(self, network: str, container: str, aliases: list[str] | None = None) -> None:
        payload = {"Container": container, "EndpointConfig": {"Aliases": aliases or []}}
        try:
            await self.request("POST", f"/networks/{network}/connect", json=payload)
        except DockerApiError as exc:
            if "already exists" not in str(exc):
                raise

    async def disconnect_network(self, network: str, container: str) -> None:
        payload = {"Container": container, "Force": True}
        try:
            await self.request("POST", f"/networks/{network}/disconnect", json=payload)
        except DockerApiError:
            pass

    async def remove_network(self, network: str) -> None:
        try:
            await self.request("DELETE", f"/networks/{network}")
        except DockerApiError:
            pass

    async def list_networks_by_run(self, audit_run_id: str) -> list[dict[str, Any]]:
        filters = {"label": [f"dieaudit.audit_run_id={audit_run_id}", "dieaudit.managed=true"]}
        return await self.request("GET", "/networks", params={"filters": json.dumps(filters)})

    async def list_managed_networks(self) -> list[dict[str, Any]]:
        filters = {"label": ["dieaudit.managed=true"]}
        return await self.request("GET", "/networks", params={"filters": json.dumps(filters)})

    async def create_container(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/containers/create", params={"name": name}, json=payload)

    async def start_container(self, container_id: str) -> None:
        await self.request("POST", f"/containers/{container_id}/start")

    async def stop_container(self, container_id: str, *, timeout_seconds: int = 1) -> None:
        try:
            await self.request("POST", f"/containers/{container_id}/stop", params={"t": timeout_seconds})
        except DockerApiError:
            pass

    async def wait_container(self, container_id: str) -> dict[str, Any]:
        response = await self.client.post(f"/containers/{container_id}/wait", timeout=None)
        if response.status_code >= 400:
            raise DockerApiError(f"wait container {container_id} failed: {response.status_code} {response.text}")
        return response.json()

    async def inspect_container(self, container_id: str) -> dict[str, Any]:
        return await self.request("GET", f"/containers/{container_id}/json")

    async def logs(self, container_id: str, *, tail: int | str = 200, timestamps: bool = True) -> str:
        response = await self.client.get(
            f"/containers/{container_id}/logs",
            params={"stdout": 1, "stderr": 1, "tail": tail, "timestamps": 1 if timestamps else 0},
        )
        if response.status_code >= 400:
            raise DockerApiError(f"GET /containers/{container_id}/logs failed: {response.status_code} {response.text}")
        return self._decode_log_stream(response.content)

    @staticmethod
    def _decode_log_stream(content: bytes) -> str:
        frames: list[bytes] = []
        offset = 0
        while offset + 8 <= len(content):
            header = content[offset : offset + 8]
            stream_type = header[0]
            size = int.from_bytes(header[4:8], "big")
            if stream_type not in {0, 1, 2} or header[1:4] != b"\x00\x00\x00" or size < 0:
                break
            payload_start = offset + 8
            payload_end = payload_start + size
            if payload_end > len(content):
                break
            frames.append(content[payload_start:payload_end])
            offset = payload_end
        if frames and offset == len(content):
            return b"".join(frames).decode("utf-8", errors="replace")
        return content.decode("utf-8", errors="replace")

    async def list_containers_by_run(self, audit_run_id: str) -> list[dict[str, Any]]:
        filters = {"label": [f"dieaudit.audit_run_id={audit_run_id}", "dieaudit.managed=true"]}
        return await self.request("GET", "/containers/json", params={"all": 1, "filters": json.dumps(filters)})

    async def list_managed_containers(self) -> list[dict[str, Any]]:
        filters = {"label": ["dieaudit.managed=true"]}
        return await self.request("GET", "/containers/json", params={"all": 1, "filters": json.dumps(filters)})

    async def remove_container(self, container_id: str, *, force: bool = True) -> None:
        try:
            await self.request("DELETE", f"/containers/{container_id}", params={"force": 1 if force else 0, "v": 1})
        except DockerApiError:
            pass

    async def run_ephemeral_container(
        self,
        *,
        name: str,
        image: str,
        command: list[str],
        labels: dict[str, str] | None = None,
        timeout_seconds: int = 30,
        network_mode: str = "none",
    ) -> dict[str, Any]:
        payload = {
            "Image": image,
            "Entrypoint": [],
            "Cmd": command,
            "Labels": labels or {},
            "HostConfig": {
                "NetworkMode": network_mode,
                "ReadonlyRootfs": True,
                "AutoRemove": False,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges:true"],
                "Memory": 256 * 1024 * 1024,
                "NanoCpus": 500_000_000,
                "PidsLimit": 128,
                "Tmpfs": {"/tmp": "rw,nosuid,size=64m"},
            },
        }
        created = await self.create_container(name, payload)
        container_id = created["Id"]
        try:
            await self.start_container(container_id)
            try:
                result = await asyncio.wait_for(self.wait_container(container_id), timeout=timeout_seconds)
            except asyncio.TimeoutError as exc:
                await self.stop_container(container_id, timeout_seconds=1)
                raise DockerApiError(f"ephemeral container timed out after {timeout_seconds}s: {name}") from exc
            logs = await self.logs(container_id, tail="all", timestamps=False)
            return {"container_id": container_id, "exit_code": result.get("StatusCode"), "logs": logs}
        finally:
            await self.remove_container(container_id, force=True)

    async def wait_for_healthy(self, container_id: str, timeout_seconds: int = 45) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last_state: dict[str, Any] = {}
        while time.monotonic() < deadline:
            info = await self.inspect_container(container_id)
            state = info.get("State", {})
            last_state = state
            health = state.get("Health", {})
            status = health.get("Status")
            if status == "healthy":
                return info
            if not health and state.get("Running"):
                return info
            if state.get("Status") in {"exited", "dead"}:
                raise DockerApiError(f"container {container_id} exited before healthy: {state}")
            await asyncio.sleep(1)
        raise DockerApiError(f"container {container_id} not healthy before timeout: {last_state}")

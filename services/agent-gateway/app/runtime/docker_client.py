class DockerRuntimeClient:
    async def health(self) -> dict:
        return {"ok": True, "mode": "skeleton"}

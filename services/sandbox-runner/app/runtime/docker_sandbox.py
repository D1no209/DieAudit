class DockerSandbox:
    async def capabilities(self) -> dict:
        return {"ok": True, "sandbox_execution_available": True, "mode": "skeleton"}

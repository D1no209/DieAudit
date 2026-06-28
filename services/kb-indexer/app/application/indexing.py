class IndexingService:
    async def status(self) -> dict:
        return {"ok": True, "documents": 0, "mode": "skeleton"}

class SearchService:
    async def search(self, query: str) -> dict:
        return {"query": query, "matches": []}

from fastapi import FastAPI

from dieaudit_common.settings import get_settings

from app.application.documents import DocumentService
from app.application.indexing import IndexingService
from app.application.search import SearchService

settings = get_settings()
app = FastAPI(title="DieAudit Knowledge Indexer", version="0.2.0")


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": settings.service_name}


@app.get("/ready")
async def ready() -> dict:
    return {"ok": True, "service": settings.service_name, "qdrant_url": settings.qdrant_url}


@app.get("/internal/knowledge/documents")
async def documents() -> list[dict]:
    return await DocumentService().list_documents()


@app.get("/internal/knowledge/status")
async def status() -> dict:
    return await IndexingService().status()


@app.post("/internal/knowledge/search")
async def search(payload: dict) -> dict:
    return await SearchService().search(str(payload.get("query") or ""))

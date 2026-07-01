from fastapi import APIRouter

router = APIRouter(prefix="/api/bff/knowledge", tags=["knowledge"])


@router.get("/documents")
async def documents() -> list[dict]:
    return []


@router.get("/status")
async def status() -> dict:
    return {"ok": True, "documents": 0, "provider": "not_configured"}


@router.post("/documents")
async def upload_document() -> dict:
    return {"ok": True, "document_id": "document-preview", "status": "accepted"}


@router.post("/search")
async def search(payload: dict) -> dict:
    return {"query": payload.get("query"), "results": []}


@router.post("/documents/{document_id}/reindex")
async def reindex(document_id: str) -> dict:
    return {"ok": True, "document_id": document_id, "status": "queued"}


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str) -> dict:
    return {"ok": True, "document_id": document_id, "deleted": True}

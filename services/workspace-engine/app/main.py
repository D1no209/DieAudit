from fastapi import FastAPI

from dieaudit_common.settings import get_settings

from app.application.imports import ImportService
from app.application.snapshots import SnapshotService
from app.application.structure import StructureService

settings = get_settings()
app = FastAPI(title="DieAudit Workspace Engine", version="0.2.0")


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": settings.service_name}


@app.get("/ready")
async def ready() -> dict:
    return {"ok": True, "service": settings.service_name, "workspace_root": str(settings.workspace_root)}


@app.post("/internal/imports")
async def import_project(payload: dict) -> dict:
    return ImportService().import_project(payload)


@app.post("/internal/snapshots")
async def create_snapshot(payload: dict) -> dict:
    return SnapshotService().create_snapshot(payload)


@app.post("/internal/structure")
async def structure(payload: dict) -> dict:
    return StructureService().inventory(payload["workspace_path"])

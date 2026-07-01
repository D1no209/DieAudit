from pathlib import Path
import shutil
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from dieaudit_common.persistence.base import SessionLocal
from dieaudit_common.persistence.repositories import ProjectRepository, SnapshotRepository
from dieaudit_common.schemas.bff import CreateProjectPayload
from dieaudit_common.settings import get_settings

from app.application.projects import ProjectApplication
from app.application.serializers import project_to_bff, snapshot_to_bff

router = APIRouter(prefix="/api/bff/projects", tags=["projects"])


@router.get("")
async def list_projects() -> list[dict]:
    async with SessionLocal() as session:
        return await ProjectApplication(session).list_projects()


@router.post("")
async def create_project(payload: CreateProjectPayload) -> dict:
    async with SessionLocal() as session:
        result = await ProjectApplication(session).create_project(payload.model_dump())
        await session.commit()
        return result


@router.post("/upload-zip")
async def upload_zip_project(name: str = Form(...), file: UploadFile = File(...)) -> dict:
    settings = get_settings()
    async with SessionLocal() as session:
        project = await ProjectRepository(session).create(name=name, source_type="upload", source_uri=file.filename, metadata={})
        snapshot_id = f"snapshot-{project.project_id.split('-', 1)[-1]}"
        workspace = Path(settings.workspace_root) / project.project_id / snapshot_id
        workspace.mkdir(parents=True, exist_ok=True)
        archive_path = Path(settings.artifact_root) / "uploads" / project.project_id / f"{snapshot_id}-{Path(file.filename or 'upload.zip').name}"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with archive_path.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(workspace)
        except zipfile.BadZipFile as exc:
            shutil.rmtree(workspace, ignore_errors=True)
            raise HTTPException(status_code=400, detail="uploaded file is not a valid zip") from exc
        snapshot = await SnapshotRepository(session).create_ready(
            project_id=project.project_id,
            workspace_path=str(workspace),
            source_type="upload",
            source_ref=file.filename,
        )
        snapshot.artifact_path = str(archive_path)
        project.status = "ready"
        project.metadata_json = {**(project.metadata_json or {}), "latest_snapshot_id": snapshot.snapshot_id}
        await session.commit()
        return {"project": project_to_bff(project), "snapshot": snapshot_to_bff(snapshot)}

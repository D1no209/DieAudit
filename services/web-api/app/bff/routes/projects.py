from fastapi import APIRouter

from dieaudit_common.persistence.base import SessionLocal
from dieaudit_common.schemas.bff import CreateProjectPayload

from app.application.projects import ProjectApplication

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

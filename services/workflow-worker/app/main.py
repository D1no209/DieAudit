from __future__ import annotations

from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from dieaudit_common.domain.models import AuditRun
from dieaudit_common.persistence.base import SessionLocal
from dieaudit_common.settings import get_settings

from app.application.pipeline_service import PipelineService

settings = get_settings()
app = FastAPI(title="DieAudit Workflow Worker", version="0.2.0")


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "service": settings.service_name}


@app.get("/ready")
async def ready() -> dict:
    return {"ok": True, "service": settings.service_name, "pipeline_model": "dag-registry"}


@app.post("/internal/pipelines/{audit_run_id}/run")
async def run_pipeline(audit_run_id: str) -> dict:
    async with SessionLocal() as session:
        audit_run = await session.scalar(select(AuditRun).where(AuditRun.audit_run_id == audit_run_id))
        if audit_run is None:
            raise HTTPException(status_code=404, detail="audit run not found")
        result = await PipelineService(session).run(audit_run)
        await session.commit()
        return result


@app.get("/internal/pipelines/registry")
async def pipeline_registry() -> dict:
    from app.pipeline.stages.default import default_stages

    return {
        "stages": [
            {
                "name": stage.name,
                "depends_on": list(stage.depends_on),
                "failure_policy": stage.failure_policy,
                "concurrency_key": stage.concurrency_key,
            }
            for stage in default_stages()
        ]
    }

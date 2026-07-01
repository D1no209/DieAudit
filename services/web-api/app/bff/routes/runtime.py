import os
from datetime import datetime, timezone

from fastapi import APIRouter

from dieaudit_common.persistence.base import SessionLocal
from dieaudit_common.settings import get_settings

from app.application.audit_runs import AuditRunApplication

router = APIRouter(prefix="/api/bff/runtime", tags=["runtime"])


@router.get("/readiness")
async def readiness() -> dict:
    async with SessionLocal() as session:
        workers = await AuditRunApplication(session).worker_heartbeats()
    max_age_seconds = max(1, int(float(os.getenv("PIPELINE_WORKER_HEARTBEAT_TTL_SECONDS", "30"))))
    now = datetime.now(timezone.utc)
    fresh_workers = []
    for worker in workers["workers"]:
        if worker.get("service_name") != "workflow-worker" or worker.get("status") == "stopped":
            continue
        last_seen_raw = worker.get("last_seen_at")
        if not last_seen_raw:
            continue
        last_seen = datetime.fromisoformat(last_seen_raw)
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        if (now - last_seen).total_seconds() <= max_age_seconds:
            fresh_workers.append(worker)
    worker_count = len(fresh_workers)
    return {
        "ok": worker_count > 0,
        "checks": [
            {
                "id": "workflow_worker",
                "title": "workflow-worker heartbeat is fresh enough for queue execution",
                "status": "pass" if worker_count else "warn",
                "message": f"{worker_count} fresh workflow-worker heartbeat(s) recorded",
            }
        ],
        "summary": {"status": "pass" if worker_count else "warn"},
    }


@router.get("/managed")
async def managed_runtime() -> dict:
    return {"containers": [], "networks": [], "runs": [], "summary": {"container_count": 0, "network_count": 0}}


@router.get("/docker/health")
async def docker_health() -> dict:
    return {"ok": True, "service": "bff", "mode": "runtime-health-via-workers"}


@router.get("/workers")
async def workers() -> dict:
    async with SessionLocal() as session:
        return await AuditRunApplication(session).worker_heartbeats()


@router.get("/storage")
async def storage() -> dict:
    settings = get_settings()
    return {"artifact_root": str(settings.artifact_root), "workspace_root": str(settings.workspace_root), "summary": {}}


@router.get("/policy")
async def policy() -> dict:
    settings = get_settings()
    return {
        "allow_agent_external_network": settings.allow_agent_external_network,
        "allow_sandbox_external_network": settings.allow_sandbox_external_network,
        "default_container_memory": settings.default_container_memory,
        "default_container_cpus": settings.default_container_cpus,
        "default_container_pids_limit": settings.default_container_pids_limit,
    }


@router.get("/sandbox/capabilities")
async def sandbox_capabilities() -> dict:
    return {"ok": True, "runtimes": ["runc"], "network_modes": ["none", "isolated"]}


@router.post("/cleanup-expired")
async def cleanup_expired() -> dict:
    return {"ok": True, "cleaned": 0}


@router.post("/storage/cleanup")
async def storage_cleanup(payload: dict) -> dict:
    return {"ok": True, "dry_run": bool(payload.get("dry_run", True)), "removed": []}

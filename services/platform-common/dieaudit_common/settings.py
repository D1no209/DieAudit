from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class CommonSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "web-api"
    postgres_async_dsn: str = "postgresql+psycopg://dieaudit:dieaudit@postgres:5432/dieaudit"
    nats_url: str = "nats://dieaudit:dieaudit@nats:4222"
    qdrant_url: str = "http://qdrant:6333"
    docker_host: str = "http://docker-socket-proxy:2375"
    api_key_header: str = "X-DieAudit-Api-Key"
    dieaudit_api_key: str = ""
    config_root: Path = Path("/app/configs")
    workspace_root: Path = Path("/dieaudit/workspaces")
    artifact_root: Path = Path("/dieaudit/artifacts")
    workspace_engine_url: str = "http://workspace-engine:8000"
    workflow_worker_url: str = "http://workflow-worker:8000"
    agent_gateway_url: str = "http://agent-gateway:8000"
    sandbox_runner_url: str = "http://sandbox-runner:8000"
    kb_indexer_url: str = "http://kb-indexer:8000"
    allow_agent_external_network: bool = True
    allow_sandbox_external_network: bool = False
    default_container_memory: str = "1024m"
    default_container_cpus: float = 1.0
    default_container_pids_limit: int = 512
    default_container_tmpfs: str = "/tmp:rw,nosuid,size=128m"


@lru_cache
def get_settings() -> CommonSettings:
    return CommonSettings()

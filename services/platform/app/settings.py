from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "web-api"
    postgres_async_dsn: str = "postgresql+psycopg://dieaudit:dieaudit@postgres:5432/dieaudit"
    config_root: Path = Path("/app/configs")
    workspace_root: Path = Path("/dieaudit/workspaces")
    artifact_root: Path = Path("/dieaudit/artifacts")
    docker_host: str = "http://docker-socket-proxy:2375"
    dynamic_container_prefix: str = "dieaudit"
    agent_gateway_container_name: str = "dieaudit-agent-gateway"
    minio_endpoint: str = "http://minio:9000"
    minio_bucket_artifacts: str = "dieaudit-artifacts"
    qdrant_url: str = "http://qdrant:6333"
    agent_gateway_url: str = "http://agent-gateway:8000"
    dieaudit_api_key: str = ""
    api_key_header: str = "X-DieAudit-Api-Key"
    default_sandbox_runtime: str = "runc"
    enable_gvisor: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()

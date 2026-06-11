from functools import lru_cache
from pathlib import Path

from pydantic_settings import SettingsConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "web-api"
    postgres_async_dsn: str = "postgresql+psycopg://dieaudit:dieaudit@postgres:5432/dieaudit"
    config_root: Path = Path("/app/configs")
    workspace_root: Path = Path("/dieaudit/workspaces")
    artifact_root: Path = Path("/dieaudit/artifacts")
    artifact_storage_backend: str = "local"
    docker_host: str = "http://docker-socket-proxy:2375"
    dynamic_container_prefix: str = "dieaudit"
    agent_gateway_container_name: str = "dieaudit-agent-gateway"
    runtime_controller_container_name: str = ""
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "dieaudit"
    minio_secret_key: str = "dieaudit-secret"
    minio_bucket_artifacts: str = "dieaudit-artifacts"
    qdrant_url: str = "http://qdrant:6333"
    knowledge_collection_name: str = "dieaudit_knowledge_v1"
    knowledge_vector_size: int = 1024
    knowledge_embedding_provider: str = "hash"
    knowledge_embedding_base_url: str = ""
    knowledge_embedding_api_key: str = ""
    knowledge_embedding_model: str = "text-embedding-3-small"
    knowledge_embedding_timeout_seconds: float = 60.0
    knowledge_embedding_probe_on_readiness: bool = True
    agent_gateway_url: str = "http://agent-gateway:8000"
    temporal_address: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "dieaudit-audit-pipeline"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    local_llm_api_key: str = ""
    dieaudit_api_key: str = ""
    api_key_header: str = "X-DieAudit-Api-Key"
    public_metrics: bool = False
    max_request_body_bytes: int = 104857600
    max_upload_bytes: int = 104857600
    max_workspace_files: int = 20000
    max_workspace_uncompressed_bytes: int = 536870912
    allowed_git_url_schemes: str = "https,ssh"
    allowed_git_hosts: str = ""
    rate_limit_per_minute: int = 120
    rate_limit_window_seconds: int = 60
    default_sandbox_runtime: str = "runc"
    enable_gvisor: bool = False
    allow_runc_sandbox: bool = True
    allow_sandbox_external_network: bool = False
    allow_agent_external_network: bool = True
    opencode_agent_timeout_seconds: int = 600
    default_container_memory: str = "1024m"
    default_container_cpus: float = 1.0
    default_container_pids_limit: int = 512
    default_container_tmpfs: str = "/tmp:rw,nosuid,size=128m"
    platform_audit_event_retention_days: int = 30
    platform_audit_event_max_rows: int = 10000
    runtime_package_retention_days: int = 7
    upload_staging_retention_days: int = 1
    unreferenced_workspace_retention_days: int = 30
    unreferenced_snapshot_retention_days: int = 90
    storage_cleanup_max_entries: int = 500
    pipeline_recovery_on_startup: bool = True
    pipeline_execution_backend: str = "workflow-worker"
    pipeline_worker_poll_interval_seconds: float = 2.0
    pipeline_worker_heartbeat_interval_seconds: float = 5.0
    pipeline_worker_heartbeat_ttl_seconds: float = 30.0
    pipeline_worker_heartbeat_retention_seconds: float = 3600.0
    enable_joern: bool = True
    joern_required: bool = True
    allow_joern_unavailable: bool = False
    joern_timeout_seconds: int = 900
    joern_query_packs: str = "entrypoints,authz,injection,file-io,network,secrets"
    enable_demo_templates: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()

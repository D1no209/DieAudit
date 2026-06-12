# DieAudit Production Readiness

This checklist covers host-level requirements that the application can detect
but cannot install safely by itself.

## Required Before Exposing The Platform

- Configure API authentication:
  - Set `DIEAUDIT_API_KEY` for a bootstrap deployment, or create persisted API
    keys with scoped permissions.
  - Keep `PUBLIC_METRICS=false` unless `/metrics` is available only on a trusted
    internal network.
- Use the workflow worker execution backend:
  - Set `PIPELINE_EXECUTION_BACKEND=workflow-worker` for the stable durable
    queue, or `PIPELINE_EXECUTION_BACKEND=temporal` to start AuditRuns through
    Temporal stage activities.
  - Keep `workflow-worker` running in the `core` Compose profile.
  - Verify `/runtime/workers` reports a fresh running worker heartbeat.
  - When using `temporal`, verify `/runtime/temporal/health` and set
    `TEMPORAL_TASK_QUEUE` consistently for API and worker services.
  - Temporal mode runs the main pipeline stages as activities; per-Finding
    Agent fan-out inside those stages is still managed by the application
    runtime and should be split into child workflows in a later hardening pass.
- Keep HTTP guard rails enabled:
  - Set `MAX_REQUEST_BODY_BYTES` to a size appropriate for source zip uploads.
  - Set `MAX_UPLOAD_BYTES` to bound streamed uploads even when
    `Content-Length` is absent or incorrect.
  - Keep `RATE_LIMIT_PER_MINUTE` greater than zero for single-node Compose
    deployments.
  - Put nginx, a WAF, or an ingress controller in front of the platform for
    distributed rate limiting in multi-node deployments.
- Keep project import guard rails enabled:
  - Set `MAX_WORKSPACE_FILES` and `MAX_WORKSPACE_UNCOMPRESSED_BYTES` to bound
    zip extraction.
  - Keep `ALLOWED_GIT_URL_SCHEMES=https,ssh` unless a deployment explicitly
    needs another remote scheme.
  - Do not allow `file://` or local Git paths in production.
- Configure local storage retention:
  - Use `/runtime/storage` to review artifact and workspace storage usage.
  - Use `/runtime/storage/cleanup` with the default `dry_run=true` before
    destructive cleanup.
  - Tune `RUNTIME_PACKAGE_RETENTION_DAYS`, `UPLOAD_STAGING_RETENTION_DAYS`,
    `UNREFERENCED_WORKSPACE_RETENTION_DAYS`, and
    `UNREFERENCED_SNAPSHOT_RETENTION_DAYS` for the deployment's evidence
    retention policy.
  - Project workspaces and snapshot archives still referenced by
    `ProjectSnapshot` records are preserved by cleanup.
- Use Docker sandbox containers for PoC execution:
  - Keep `DEFAULT_SANDBOX_RUNTIME=runc` unless the deployment explicitly
    registers another Docker runtime.
  - Keep `ALLOW_RUNC_SANDBOX=true` when using the default Docker runtime.
  - Keep `ALLOW_SANDBOX_EXTERNAL_NETWORK=false` unless a specific validation
    target requires outbound network access.
- Optionally configure semantic knowledge embeddings:
  - Set `KNOWLEDGE_EMBEDDING_PROVIDER=openai-compatible`.
  - Set `KNOWLEDGE_EMBEDDING_BASE_URL` to an endpoint that exposes
    `/embeddings`.
  - Set `KNOWLEDGE_EMBEDDING_MODEL` to an embedding model, not a chat model.
  - Set `KNOWLEDGE_VECTOR_SIZE` to the embedding dimension returned by the
    provider.
  - Set `KNOWLEDGE_EMBEDDING_API_KEY` if the provider requires authentication.

## Local Testing Exceptions

The default sandbox mode uses Docker `runc` container isolation. It is the
baseline supported deployment mode for DieAudit.

The `hash` knowledge embedding provider is deterministic and useful for local
smoke tests. It is not semantic retrieval; configure an OpenAI-compatible
embedding provider when knowledge-base relevance quality matters.

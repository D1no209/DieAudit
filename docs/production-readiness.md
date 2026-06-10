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
  - Set `PIPELINE_EXECUTION_BACKEND=workflow-worker`.
  - Keep `workflow-worker` running in the `core` Compose profile.
  - Verify `/runtime/workers` reports a fresh running worker heartbeat.
- Keep HTTP guard rails enabled:
  - Set `MAX_REQUEST_BODY_BYTES` to a size appropriate for source zip uploads.
  - Keep `RATE_LIMIT_PER_MINUTE` greater than zero for single-node Compose
    deployments.
  - Put nginx, a WAF, or an ingress controller in front of the platform for
    distributed rate limiting in multi-node deployments.
- Use a strong sandbox runtime for untrusted PoC execution:
  - Install gVisor `runsc` or another strong runtime such as Kata.
  - Register the runtime in Docker Engine and restart Docker.
  - Set `ENABLE_GVISOR=true` and `DEFAULT_SANDBOX_RUNTIME=runsc`.
  - Keep `ALLOW_RUNC_SANDBOX=false` in production.
- Configure semantic knowledge embeddings:
  - Set `KNOWLEDGE_EMBEDDING_PROVIDER=openai-compatible`.
  - Set `KNOWLEDGE_EMBEDDING_BASE_URL` to an endpoint that exposes
    `/embeddings`.
  - Set `KNOWLEDGE_EMBEDDING_MODEL` to an embedding model, not a chat model.
  - Set `KNOWLEDGE_VECTOR_SIZE` to the embedding dimension returned by the
    provider.
  - Set `KNOWLEDGE_EMBEDDING_API_KEY` if the provider requires authentication.

## Local Testing Exceptions

`ALLOW_RUNC_SANDBOX=true` allows Docker `runc` based sandbox execution for
trusted local tests only. It is not production isolation and readiness will
continue to require a strong runtime.

The `hash` knowledge embedding provider is deterministic and useful for local
smoke tests. It is not semantic retrieval and should not be used for production
RAG.

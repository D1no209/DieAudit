# DieAudit

DieAudit is a local-first, multi-agent code audit platform. The current implementation focuses on a runnable Docker Compose environment, Docker runtime orchestration for Agent containers and MCP sidecars, OpenCode ACP agents, project import, SCA/static tooling, structured findings, validator attempts, sandbox-assisted PoC execution, and a Qdrant-backed knowledge base.

## Quick Start

The default proxy is `http://127.0.0.1:7897` for Docker CLI pulls and `http://host.docker.internal:7897` for Docker build steps. Override `HOST_HTTP_PROXY`, `HOST_HTTPS_PROXY`, `BUILD_HTTP_PROXY`, and `BUILD_HTTPS_PROXY` in `.env` if needed.

```powershell
copy .env.example .env
.\scripts\bootstrap.ps1
```

Open:

- Web UI: http://localhost:8080
- Web API: http://localhost:18000/health
- Agent Gateway: http://localhost:18001/health
- Temporal UI: http://localhost:18088
- MinIO Console: http://localhost:19001

## Demo Runtime Orchestration

Build the demo Agent/MCP images and start the core platform:

```powershell
docker compose --profile demo build
docker compose --profile core up -d
```

Start a mock Agent with mock MCP sidecars:

```powershell
Invoke-RestMethod -Method Post http://localhost:18001/audit-runs/demo-run/demo
```

List dynamic containers:

```powershell
Invoke-RestMethod http://localhost:18001/audit-runs/demo-run/containers
```

Clean up the dynamic run network and containers:

```powershell
Invoke-RestMethod -Method Post http://localhost:18001/audit-runs/demo-run/cleanup
```

## Runtime Model

- `agent-gateway` and `sandbox-runner` talk to Docker through `docker-socket-proxy`.
- Dynamic containers are labeled with `dieaudit.managed=true`, `dieaudit.audit_run_id`, `dieaudit.project_id`, `dieaudit.role`, and `dieaudit.ttl`.
- Each AuditRun gets a dedicated Docker network named `dieaudit-run-{audit_run_id}`.
- Agent templates live in `configs/agent-templates`.
- MCP templates live in `configs/mcp-templates`.
- Mock Agent images remain only as demo fixtures. Production OpenCode templates are in `configs/agent-templates/opencode-*.yaml`.
- MCP templates in `configs/mcp-templates` use `dieaudit/tool-mcp:local`; heavy Joern/CodeQL CLIs return structured `available=false` until installed in that image or replaced by dedicated tool images.

## Knowledge Base Embeddings

The knowledge base defaults to deterministic local hash embeddings so Compose works without an external embedding service. For production semantic retrieval, configure an OpenAI-compatible embeddings endpoint and use a dedicated Qdrant collection:

```env
KNOWLEDGE_EMBEDDING_PROVIDER=openai-compatible
KNOWLEDGE_EMBEDDING_BASE_URL=https://embedding-provider.example/v1
KNOWLEDGE_EMBEDDING_API_KEY=...
KNOWLEDGE_EMBEDDING_MODEL=text-embedding-3-small
KNOWLEDGE_VECTOR_SIZE=1536
KNOWLEDGE_COLLECTION_NAME=dieaudit_knowledge_embeddings_v1
```

Do not reuse an existing Qdrant collection when changing embedding dimension or provider. Reindex uploaded knowledge documents after changing these settings.

## Agent Protocols

The gateway includes both selected protocol SDKs:

- `agent-client-protocol` for stdio JSON-RPC Agent Client Protocol agents.
- `a2a-sdk` for A2A HTTP agent-to-agent clients.

Check SDK availability and template readiness:

```powershell
Invoke-RestMethod http://localhost:18001/runtime/protocols
```

## Persistence And Database

The platform uses SQLAlchemy ORM models and creates the first schema on `web-api` startup. Raw SQL is not required for the application schema.

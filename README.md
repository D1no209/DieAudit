# DieAudit

DieAudit is a local-first, multi-agent code audit platform. The current implementation focuses on a runnable Docker Compose environment, Docker runtime orchestration for Agent containers and MCP sidecars, OpenCode ACP agents, project import, SCA/static tooling, structured findings, validator attempts, sandbox-assisted PoC execution, and a Qdrant-backed knowledge base.

## Quick Start

The default proxy is `http://127.0.0.1:7897` for Docker CLI pulls and `http://host.docker.internal:7897` for Docker build steps. Override `HOST_HTTP_PROXY`, `HOST_HTTPS_PROXY`, `BUILD_HTTP_PROXY`, and `BUILD_HTTPS_PROXY` in `.env` if needed.

```powershell
copy .env.example .env
.\scripts\bootstrap.ps1
```

The bootstrap script builds the core production path by default. It does not build or expose mock demo images unless explicitly requested.

Open:

- Web UI: http://localhost:8080
- Web API: http://localhost:18000/health
- Agent Gateway: http://localhost:18001/health
- Temporal UI: http://localhost:18088
- MinIO Console: http://localhost:19001

## Production Readiness

Use `.env.production.example` as the deployment checklist. Do not commit the resulting `.env`.

Required before exposing the platform:

- Set `DIEAUDIT_API_KEY` or create a persisted active API key through the UI/API.
- Keep `PUBLIC_METRICS=false` unless metrics are protected by a separate private network or auth layer.
- Keep `PIPELINE_EXECUTION_BACKEND=workflow-worker`; `background-tasks` is only for local debugging.
- Keep `ENABLE_DEMO_TEMPLATES=false`; mock demo templates are hidden from production runtime APIs by default.
- Install gVisor `runsc` or another strong container runtime, then set `ENABLE_GVISOR=true` and `DEFAULT_SANDBOX_RUNTIME=runsc`.
- Keep `ALLOW_RUNC_SANDBOX=false` for untrusted PoC execution.
- Keep `ALLOW_SANDBOX_EXTERNAL_NETWORK=false` unless a specific sandbox/PoC test requires outbound network access.
- Configure semantic KB embeddings with `KNOWLEDGE_EMBEDDING_PROVIDER=openai-compatible` and reindex documents into a fresh Qdrant collection.
- Build the optional heavy analyzer MCP images before relying on Joern/CodeQL templates: `docker compose --profile tools build tool-mcp-codeql-image tool-mcp-joern-image`.

Check the live deployment:

```powershell
Invoke-RestMethod http://localhost:8080/gateway/runtime/readiness | ConvertTo-Json -Depth 10
```

The Compose default now queues audit pipelines for `workflow-worker`; the API process no longer owns pipeline execution through request-local background tasks.

Check sandbox runtime visibility from both Docker and the platform:

```powershell
docker info --format '{{json .Runtimes}}'
docker compose --profile core config | Select-String "DEFAULT_SANDBOX_RUNTIME|ENABLE_GVISOR|ALLOW_RUNC_SANDBOX|ALLOW_SANDBOX_EXTERNAL_NETWORK"
Invoke-RestMethod http://localhost:8080/gateway/runtime/sandbox/capabilities | ConvertTo-Json -Depth 10
```

Check MCP tool image capabilities:

```powershell
Invoke-RestMethod http://localhost:8080/gateway/runtime/tool-capabilities | ConvertTo-Json -Depth 10
```

MCP templates can declare `required_binaries`; readiness probes the configured image with a short-lived isolated container and reports missing CLIs such as `codeql` or `joern`. CodeQL and Joern use dedicated heavy images (`dieaudit/tool-mcp-codeql:local`, `dieaudit/tool-mcp-joern:local`) so the default tool image stays lightweight.

Create the first persisted admin key from the running Compose environment without opening an unauthenticated browser/API setup flow:

```powershell
.\scripts\create-api-key.ps1 -Name bootstrap-admin -Scope admin
```

Linux/macOS equivalent:

```bash
NAME=bootstrap-admin SCOPES=admin ./scripts/create-api-key.sh
```

The command prints the API key once and stores only its hash in Postgres. Use the printed key as `X-DieAudit-Api-Key`.

## Demo Profile Runtime Orchestration

Demo fixtures are intentionally excluded from the default startup path. Use them only for smoke tests on a local machine:

```powershell
echo ENABLE_DEMO_TEMPLATES=true >> .env
.\scripts\bootstrap.ps1 -IncludeDemo
docker compose --profile core up -d
```

Linux/macOS equivalent:

```bash
echo ENABLE_DEMO_TEMPLATES=true >> .env
./scripts/bootstrap.sh --include-demo
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
- Mock Agent images remain only as demo fixtures. Production OpenCode templates are in `configs/agent-templates/opencode-*.yaml`, with bare role aliases such as `orchestrator` and `validator` also pointing at the OpenCode runtime.
- Standard MCP templates in `configs/mcp-templates` use `dieaudit/tool-mcp:local`; heavy Joern/CodeQL templates use dedicated images built by the `tools` profile.

## Knowledge Base Embeddings

The knowledge base defaults to deterministic local hash embeddings so Compose works without an external embedding service. For production semantic retrieval, configure an OpenAI-compatible embeddings endpoint and use a dedicated Qdrant collection:

```env
KNOWLEDGE_EMBEDDING_PROVIDER=openai-compatible
KNOWLEDGE_EMBEDDING_BASE_URL=https://embedding-provider.example/v1
KNOWLEDGE_EMBEDDING_API_KEY=...
KNOWLEDGE_EMBEDDING_MODEL=text-embedding-3-small
KNOWLEDGE_VECTOR_SIZE=1536
KNOWLEDGE_COLLECTION_NAME=dieaudit_knowledge_embeddings_v1
KNOWLEDGE_EMBEDDING_PROBE_ON_READINESS=true
```

`/runtime/readiness` and `/knowledge/status` probe a configured semantic provider by requesting one embedding and checking the returned vector dimension. Do not reuse an existing Qdrant collection when changing embedding dimension or provider. Reindex uploaded knowledge documents after changing these settings.

## Artifact Access

Reports, evidence files, snapshots, container logs, tool output, and knowledge uploads are stored under `ARTIFACT_ROOT`. Use the platform API instead of exposing the host directory:

```powershell
Invoke-RestMethod "http://localhost:18001/artifacts/metadata?path=reports/run-id/report.md"
Invoke-WebRequest "http://localhost:18001/artifacts/download?path=reports/run-id/report.md" -OutFile report.md
```

Artifact download endpoints reject missing files, directories, and paths outside `ARTIFACT_ROOT`.

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

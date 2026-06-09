# DieAudit

DieAudit is a local-first, multi-agent code audit platform skeleton. This first implementation focuses on a runnable Docker Compose environment and a working Docker runtime orchestration path for Agent containers and MCP sidecars.

## Quick Start

The first build needs access to Docker Hub for base images such as Python, Node, Nginx, Postgres, Redis, NATS, Qdrant, and Temporal. If your network blocks Docker Hub, pre-pull or mirror those images first.

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
- Mock Agent and MCP images prove that the platform can inject `MCP_SERVERS_JSON` and connect Agent containers to sidecars.

## Persistence And Database

The platform uses SQLAlchemy ORM models and creates the first schema on `web-api` startup. Raw SQL is not required for the application schema.

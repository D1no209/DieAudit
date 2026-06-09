$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

New-Item -ItemType Directory -Force -Path "data/workspaces", "data/artifacts" | Out-Null

docker compose --profile demo build
docker compose --profile core up -d

Write-Host ""
Write-Host "DieAudit is starting:"
Write-Host "  Web:          http://localhost:8080"
Write-Host "  API:          http://localhost:18000/health"
Write-Host "  AgentGateway: http://localhost:18001/health"
Write-Host "  Temporal UI:  http://localhost:18088"
Write-Host "  MinIO:        http://localhost:19001"

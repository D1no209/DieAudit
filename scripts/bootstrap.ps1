param(
    [switch]$IncludeDemo
)

$ErrorActionPreference = "Stop"

$env:HTTP_PROXY = if ($env:HOST_HTTP_PROXY) { $env:HOST_HTTP_PROXY } else { "http://127.0.0.1:7897" }
$env:HTTPS_PROXY = if ($env:HOST_HTTPS_PROXY) { $env:HOST_HTTPS_PROXY } else { "http://127.0.0.1:7897" }
$env:http_proxy = $env:HTTP_PROXY
$env:https_proxy = $env:HTTPS_PROXY
$env:NO_PROXY = if ($env:NO_PROXY) { $env:NO_PROXY } else { "localhost,127.0.0.1,::1" }
$env:no_proxy = $env:NO_PROXY

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

New-Item -ItemType Directory -Force -Path "data/workspaces", "data/artifacts" | Out-Null

if ($IncludeDemo) {
    docker compose --profile demo build
} else {
    docker compose --profile core build
}
docker compose --profile core up -d

Write-Host ""
Write-Host "DieAudit is starting:"
Write-Host "  Web:          http://localhost:8080"
Write-Host "  API:          http://localhost:18000/health"
Write-Host "  AgentGateway: http://localhost:18001/health"
Write-Host "  Temporal UI:  http://localhost:18088"
Write-Host "  MinIO:        http://localhost:19001"

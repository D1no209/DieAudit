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

$images = @(
    "dieaudit/tool-mcp-joern:local",
    "semgrep/semgrep:latest",
    "aquasec/trivy:latest",
    "anchore/syft:latest",
    "ghcr.io/joernio/joern:master"
)

docker compose --profile tools build tool-mcp-image tool-mcp-joern-image opencode-agent-image
if ($IncludeDemo) {
    docker compose --profile demo build mock-agent-image mock-mcp-image
}

foreach ($image in $images) {
    if ($image -like "dieaudit/*:local") {
        continue
    }
    Write-Host "Pulling $image"
    docker pull $image
}

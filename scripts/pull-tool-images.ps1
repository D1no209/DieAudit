$ErrorActionPreference = "Stop"

$images = @(
    "dieaudit/mock-agent:local",
    "dieaudit/mock-mcp:local",
    "semgrep/semgrep:latest",
    "aquasec/trivy:latest",
    "anchore/syft:latest",
    "ghcr.io/joernio/joern:latest",
    "ghcr.io/github/codeql-cli/codeql-cli:latest"
)

docker compose --profile tools build

foreach ($image in $images) {
    if ($image -like "dieaudit/*:local") {
        continue
    }
    Write-Host "Pulling $image"
    docker pull $image
}

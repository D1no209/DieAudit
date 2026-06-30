#!/usr/bin/env bash
set -euo pipefail

include_demo=false
if [ "${1:-}" = "--include-demo" ]; then
  include_demo=true
fi

export HTTP_PROXY="${HOST_HTTP_PROXY:-http://127.0.0.1:7897}"
export HTTPS_PROXY="${HOST_HTTPS_PROXY:-http://127.0.0.1:7897}"
export http_proxy="${HTTP_PROXY}"
export https_proxy="${HTTPS_PROXY}"
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1}"
export no_proxy="${NO_PROXY}"

docker compose --profile tools build tool-mcp-image kimi-code-agent-image
if [ "${include_demo}" = "true" ]; then
  docker compose --profile demo build mock-agent-image mock-mcp-image
fi

images=(
  semgrep/semgrep:latest
  aquasec/trivy:latest
  anchore/syft:latest
)

for image in "${images[@]}"; do
  echo "Pulling ${image}"
  docker pull "${image}"
done

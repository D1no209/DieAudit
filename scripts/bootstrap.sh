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

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

mkdir -p data/workspaces data/artifacts

if [ "${include_demo}" = "true" ]; then
  docker compose --profile demo build
else
  docker compose --profile core build
fi
docker compose --profile core up -d

cat <<'EOF'

DieAudit is starting:
  Web:          http://localhost:8080
  API:          http://localhost:18000/health
  AgentGateway: http://localhost:18001/health
  Temporal UI:  http://localhost:18088
EOF

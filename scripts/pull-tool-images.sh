#!/usr/bin/env bash
set -euo pipefail

export HTTP_PROXY="${HOST_HTTP_PROXY:-http://127.0.0.1:7897}"
export HTTPS_PROXY="${HOST_HTTPS_PROXY:-http://127.0.0.1:7897}"
export http_proxy="${HTTP_PROXY}"
export https_proxy="${HTTPS_PROXY}"
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1}"
export no_proxy="${NO_PROXY}"

docker compose --profile tools build

images=(
  semgrep/semgrep:latest
  aquasec/trivy:latest
  anchore/syft:latest
  ghcr.io/joernio/joern:master
)

for image in "${images[@]}"; do
  echo "Pulling ${image}"
  docker pull "${image}"
done

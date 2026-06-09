#!/usr/bin/env bash
set -euo pipefail

docker compose --profile tools build

images=(
  semgrep/semgrep:latest
  aquasec/trivy:latest
  anchore/syft:latest
  ghcr.io/joernio/joern:latest
  ghcr.io/github/codeql-cli/codeql-cli:latest
)

for image in "${images[@]}"; do
  echo "Pulling ${image}"
  docker pull "${image}"
done

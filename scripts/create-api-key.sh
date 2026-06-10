#!/usr/bin/env bash
set -euo pipefail

NAME="${NAME:-bootstrap-admin}"
SCOPES="${SCOPES:-admin}"
METADATA_JSON="${METADATA_JSON:-{}}"
JSON_OUTPUT="${JSON_OUTPUT:-false}"

args=(
  compose
  exec
  -T
  web-api
  python
  -m
  app.cli.create_api_key
  --name
  "$NAME"
  --metadata-json
  "$METADATA_JSON"
)

IFS=',' read -ra scope_parts <<< "$SCOPES"
for scope in "${scope_parts[@]}"; do
  if [[ -n "${scope// /}" ]]; then
    args+=(--scope "$scope")
  fi
done

if [[ "$JSON_OUTPUT" == "true" ]]; then
  args+=(--json)
fi

docker "${args[@]}"

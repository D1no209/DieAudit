#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080/gateway}"
API_KEY="${DIEAUDIT_API_KEY:-}"
API_KEY_HEADER="${API_KEY_HEADER:-X-DieAudit-Api-Key}"
START_COMPOSE="${START_COMPOSE:-false}"
RUN_PIPELINE="${RUN_PIPELINE:-false}"
USE_TEMPORAL="${USE_TEMPORAL:-false}"
SKIP_CLEANUP="${SKIP_CLEANUP:-false}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-900}"

export HTTP_PROXY="${HOST_HTTP_PROXY:-http://127.0.0.1:7897}"
export HTTPS_PROXY="${HOST_HTTPS_PROXY:-http://127.0.0.1:7897}"
export http_proxy="${HTTP_PROXY}"
export https_proxy="${HTTPS_PROXY}"
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1}"
export no_proxy="${NO_PROXY}"

json() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  if [ -n "${body}" ]; then
    if [ -n "${API_KEY}" ]; then
      curl -fsS -X "${method}" -H "${API_KEY_HEADER}: ${API_KEY}" -H "Content-Type: application/json" -d "${body}" "${BASE_URL}${path}"
    else
      curl -fsS -X "${method}" -H "Content-Type: application/json" -d "${body}" "${BASE_URL}${path}"
    fi
  else
    if [ -n "${API_KEY}" ]; then
      curl -fsS -X "${method}" -H "${API_KEY_HEADER}: ${API_KEY}" "${BASE_URL}${path}"
    else
      curl -fsS -X "${method}" "${BASE_URL}${path}"
    fi
  fi
}

if [ "${START_COMPOSE}" = "true" ]; then
  if [ "${USE_TEMPORAL}" = "true" ]; then
    export PIPELINE_EXECUTION_BACKEND=temporal
  fi
  docker compose --profile core up -d
  if [ "${USE_TEMPORAL}" = "true" ]; then
    docker compose --profile core up -d --force-recreate web-api workflow-worker
  fi
fi

deadline=$((SECONDS + 180))
until json GET /health >/dev/null 2>&1; do
  if [ "${SECONDS}" -ge "${deadline}" ]; then
    echo "DieAudit API did not become healthy at ${BASE_URL}" >&2
    exit 1
  fi
  sleep 3
done

status="$(json GET /runtime/e2e/status)"
model_configured="$(python -c 'import json,sys; print(str(bool(json.load(sys.stdin)["checks"]["model_configured"])).lower())' <<<"${status}")"
pipeline_backend="$(python -c 'import json,sys; print(json.load(sys.stdin).get("pipeline_backend") or "")' <<<"${status}")"
should_run_pipeline="${RUN_PIPELINE}"
if [ "${model_configured}" = "true" ] || [ "${USE_TEMPORAL}" = "true" ]; then
  should_run_pipeline="true"
fi
if [ "${USE_TEMPORAL}" = "true" ] && [ "${pipeline_backend}" != "temporal" ]; then
  echo "USE_TEMPORAL was requested, but runtime pipeline_backend is '${pipeline_backend}'. Recreate web-api and workflow-worker with PIPELINE_EXECUTION_BACKEND=temporal." >&2
  exit 1
fi

work_root="$(mktemp -d)"
project_dir="${work_root}/project"
mkdir -p "${project_dir}"
cat >"${project_dir}/app.py" <<'PY'
import os
from flask import Flask, request

app = Flask(__name__)

@app.get("/debug")
def debug():
    path = request.args.get("path", "")
    return open(path).read() if path else os.getcwd()
PY
printf 'flask==2.2.2\n' >"${project_dir}/requirements.txt"
zip_path="${work_root}/project.zip"
(cd "${project_dir}" && python -m zipfile -c "${zip_path}" app.py requirements.txt)

project_name="dieaudit-e2e-$(date +%Y%m%d%H%M%S)"
if [ -n "${API_KEY}" ]; then
  upload="$(curl -fsS -X POST -H "${API_KEY_HEADER}: ${API_KEY}" -F "name=${project_name}" -F "file=@${zip_path}" "${BASE_URL}/projects/upload-zip")"
else
  upload="$(curl -fsS -X POST -F "name=${project_name}" -F "file=@${zip_path}" "${BASE_URL}/projects/upload-zip")"
fi
project_id="$(python -c 'import json,sys; print(json.load(sys.stdin)["project"]["project_id"])' <<<"${upload}")"
snapshot_id="$(python -c 'import json,sys; print(json.load(sys.stdin)["snapshot"]["snapshot_id"])' <<<"${upload}")"

audit_body="$(python -c 'import json,sys; print(json.dumps({"snapshot_id": sys.argv[1], "start_agent": False, "validator_rounds": 1, "max_parallel_validators": 1, "retain_runtime_on_failure": True, "input_payload": {"goal": "Run an E2E smoke audit for the intentionally small Python fixture. Return structured JSON findings if evidence is found."}}))' "${snapshot_id}")"
created="$(json POST "/projects/${project_id}/audit-runs" "${audit_body}")"
audit_run_id="$(python -c 'import json,sys; print(json.load(sys.stdin)["audit_run"]["audit_run_id"])' <<<"${created}")"

if [ "${should_run_pipeline}" = "true" ]; then
  json POST "/audit-runs/${audit_run_id}/run-pipeline" >/dev/null
  deadline=$((SECONDS + TIMEOUT_SECONDS))
  run_status=""
  while [ "${SECONDS}" -lt "${deadline}" ]; do
    sleep 5
    pipeline="$(json GET "/audit-runs/${audit_run_id}/pipeline-status")"
    run_status="$(python -c 'import json,sys; print(json.load(sys.stdin)["audit_run"]["status"])' <<<"${pipeline}")"
    case "${run_status}" in
      completed|completed_with_warnings|failed|cancelled) break ;;
    esac
  done
  if [ "${run_status}" != "completed" ] && [ "${run_status}" != "completed_with_warnings" ]; then
    echo "pipeline did not complete successfully: ${run_status}" >&2
    exit 1
  fi
  if [ "${USE_TEMPORAL}" = "true" ]; then
    events="$(json GET "/audit-runs/${audit_run_id}/events")"
    temporal_observed="$(python -c 'import json,sys; events=json.load(sys.stdin); print(str(any(str(e.get("event_type","")).startswith("temporal_") or (isinstance(e.get("payload"), dict) and e["payload"].get("backend") == "temporal") for e in events)).lower())' <<<"${events}")"
    if [ "${temporal_observed}" != "true" ]; then
      echo "USE_TEMPORAL was requested, but no Temporal backend audit event was observed for ${audit_run_id}" >&2
      exit 1
    fi
  fi
else
  finding_body='{"title":"E2E control-plane smoke finding","severity":"low","status":"needs_review","file_path":"app.py","line_start":7,"description":"Synthetic finding used only to validate persistence and report generation without a model key.","source":"e2e-smoke","raw":{"skipped_pipeline":true}}'
  json POST "/audit-runs/${audit_run_id}/findings" "${finding_body}" >/dev/null
  json POST "/audit-runs/${audit_run_id}/report" >/dev/null
fi

agent_runs="$(json GET "/audit-runs/${audit_run_id}/agent-runs")"
findings="$(json GET "/audit-runs/${audit_run_id}/findings")"
evidence="$(json GET "/audit-runs/${audit_run_id}/evidence")"
attempts="$(json GET "/audit-runs/${audit_run_id}/validation-attempts")"
reports="$(json GET "/audit-runs/${audit_run_id}/reports")"
containers="$(json GET "/audit-runs/${audit_run_id}/containers")"
final_pipeline="$(json GET "/audit-runs/${audit_run_id}/pipeline-status")"

report_count="$(python -c 'import json,sys; print(len(json.load(sys.stdin)))' <<<"${reports}")"
if [ "${report_count}" -lt 1 ]; then
  echo "expected at least one report artifact" >&2
  exit 1
fi

cleanup_json="null"
if [ "${SKIP_CLEANUP}" != "true" ]; then
  cleanup_json="$(json POST "/audit-runs/${audit_run_id}/cleanup")"
fi

printf '%s' "${agent_runs}" >"${work_root}/agent_runs.json"
printf '%s' "${findings}" >"${work_root}/findings.json"
printf '%s' "${evidence}" >"${work_root}/evidence.json"
printf '%s' "${attempts}" >"${work_root}/attempts.json"
printf '%s' "${reports}" >"${work_root}/reports.json"
printf '%s' "${containers}" >"${work_root}/containers.json"
printf '%s' "${cleanup_json}" >"${work_root}/cleanup.json"
printf '%s' "${final_pipeline}" >"${work_root}/pipeline.json"

python - "${should_run_pipeline}" "${audit_run_id}" "${project_id}" "${model_configured}" "${work_root}" "${pipeline_backend}" "${USE_TEMPORAL}" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[5])
pipeline = json.loads((root / "pipeline.json").read_text())
payloads = [
    json.loads((root / "agent_runs.json").read_text()),
    json.loads((root / "findings.json").read_text()),
    json.loads((root / "evidence.json").read_text()),
    json.loads((root / "attempts.json").read_text()),
    json.loads((root / "reports.json").read_text()),
    json.loads((root / "containers.json").read_text()),
]
print(json.dumps({
    "ok": True,
    "mode": "pipeline" if sys.argv[1] == "true" else "control-plane",
    "pipeline_backend": sys.argv[6],
    "temporal_required": sys.argv[7] == "true",
    "pipeline_status": pipeline["audit_run"]["status"],
    "audit_run_id": sys.argv[2],
    "project_id": sys.argv[3],
    "model_configured": sys.argv[4] == "true",
    "counts": {
        "agent_runs": len(payloads[0]),
        "findings": len(payloads[1]),
        "evidence": len(payloads[2]),
        "validation_attempts": len(payloads[3]),
        "reports": len(payloads[4]),
        "containers": len(payloads[5]),
    },
    "cleanup": json.loads((root / "cleanup.json").read_text()),
}, indent=2))
PY

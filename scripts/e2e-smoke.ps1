param(
    [string]$BaseUrl = "http://localhost:8080/gateway",
    [string]$ApiKey = $env:DIEAUDIT_API_KEY,
    [string]$ApiKeyHeader = $(if ($env:API_KEY_HEADER) { $env:API_KEY_HEADER } else { "X-DieAudit-Api-Key" }),
    [switch]$StartCompose,
    [switch]$RunPipeline,
    [switch]$SkipCleanup,
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = "Stop"

$env:HTTP_PROXY = if ($env:HOST_HTTP_PROXY) { $env:HOST_HTTP_PROXY } else { "http://127.0.0.1:7897" }
$env:HTTPS_PROXY = if ($env:HOST_HTTPS_PROXY) { $env:HOST_HTTPS_PROXY } else { "http://127.0.0.1:7897" }
$env:http_proxy = $env:HTTP_PROXY
$env:https_proxy = $env:HTTPS_PROXY
$env:NO_PROXY = if ($env:NO_PROXY) { $env:NO_PROXY } else { "localhost,127.0.0.1,::1" }
$env:no_proxy = $env:NO_PROXY

$headers = @{}
if ($ApiKey) {
    $headers[$ApiKeyHeader] = $ApiKey
}

function Invoke-DieAuditJson {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [string]$Method = "GET",
        [object]$Body = $null
    )
    $uri = "$BaseUrl$Path"
    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
    }
    $json = $Body | ConvertTo-Json -Depth 20
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body $json
}

function Wait-DieAuditHealth {
    $deadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-DieAuditJson -Path "/health"
            if ($health.ok) { return }
        } catch {
            Start-Sleep -Seconds 3
        }
    }
    throw "DieAudit API did not become healthy at $BaseUrl"
}

if ($StartCompose) {
    docker compose --profile core up -d
}

Wait-DieAuditHealth
$status = Invoke-DieAuditJson -Path "/runtime/e2e/status"
$modelConfigured = [bool]($status.checks.model_configured)
$shouldRunPipeline = [bool]($RunPipeline -or $modelConfigured)

$workRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("dieaudit-e2e-" + [Guid]::NewGuid().ToString("N"))
$projectDir = Join-Path $workRoot "project"
New-Item -ItemType Directory -Force -Path $projectDir | Out-Null
Set-Content -Path (Join-Path $projectDir "app.py") -Encoding UTF8 -Value @"
import os
from flask import Flask, request

app = Flask(__name__)

@app.get("/debug")
def debug():
    path = request.args.get("path", "")
    return open(path).read() if path else os.getcwd()
"@
Set-Content -Path (Join-Path $projectDir "requirements.txt") -Encoding UTF8 -Value "flask==2.2.2"
$zipPath = Join-Path $workRoot "project.zip"
Compress-Archive -Path (Join-Path $projectDir "*") -DestinationPath $zipPath -Force

$projectName = "dieaudit-e2e-" + (Get-Date -Format "yyyyMMddHHmmss")
$upload = Invoke-RestMethod -Method POST -Uri "$BaseUrl/projects/upload-zip" -Headers $headers -Form @{
    name = $projectName
    file = Get-Item -LiteralPath $zipPath
}
$projectId = $upload.project.project_id
$snapshotId = $upload.snapshot.snapshot_id

$auditRunBody = @{
    snapshot_id = $snapshotId
    start_agent = $false
    validator_rounds = 1
    max_parallel_validators = 1
    retain_runtime_on_failure = $true
    input_payload = @{
        goal = "Run an E2E smoke audit for the intentionally small Python fixture. Return structured JSON findings if evidence is found."
    }
}
$created = Invoke-DieAuditJson -Method POST -Path "/projects/$projectId/audit-runs" -Body $auditRunBody
$auditRunId = $created.audit_run.audit_run_id

if ($shouldRunPipeline) {
    Invoke-DieAuditJson -Method POST -Path "/audit-runs/$auditRunId/run-pipeline" | Out-Null
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 5
        $pipeline = Invoke-DieAuditJson -Path "/audit-runs/$auditRunId/pipeline-status"
        $runStatus = $pipeline.audit_run.status
        if ($runStatus -in @("completed", "completed_with_warnings", "failed", "cancelled")) {
            break
        }
    } while ((Get-Date) -lt $deadline)
    if ($runStatus -notin @("completed", "completed_with_warnings")) {
        throw "pipeline did not complete successfully: $runStatus"
    }
} else {
    Invoke-DieAuditJson -Method POST -Path "/audit-runs/$auditRunId/findings" -Body @{
        title = "E2E control-plane smoke finding"
        severity = "low"
        status = "needs_review"
        file_path = "app.py"
        line_start = 7
        description = "Synthetic finding used only to validate persistence and report generation without a model key."
        source = "e2e-smoke"
        raw = @{ skipped_pipeline = $true }
    } | Out-Null
    Invoke-DieAuditJson -Method POST -Path "/audit-runs/$auditRunId/report" | Out-Null
}

$agentRuns = Invoke-DieAuditJson -Path "/audit-runs/$auditRunId/agent-runs"
$findings = Invoke-DieAuditJson -Path "/audit-runs/$auditRunId/findings"
$evidence = Invoke-DieAuditJson -Path "/audit-runs/$auditRunId/evidence"
$attempts = Invoke-DieAuditJson -Path "/audit-runs/$auditRunId/validation-attempts"
$reports = Invoke-DieAuditJson -Path "/audit-runs/$auditRunId/reports"
$containers = Invoke-DieAuditJson -Path "/audit-runs/$auditRunId/containers"

if (-not $reports -or $reports.Count -lt 1) {
    throw "expected at least one report artifact"
}

$cleanup = $null
if (-not $SkipCleanup) {
    $cleanup = Invoke-DieAuditJson -Method POST -Path "/audit-runs/$auditRunId/cleanup"
}

[pscustomobject]@{
    ok = $true
    mode = $(if ($shouldRunPipeline) { "pipeline" } else { "control-plane" })
    audit_run_id = $auditRunId
    project_id = $projectId
    model_configured = $modelConfigured
    counts = @{
        agent_runs = $agentRuns.Count
        findings = $findings.Count
        evidence = $evidence.Count
        validation_attempts = $attempts.Count
        reports = $reports.Count
        containers = $containers.Count
    }
    cleanup = $cleanup
} | ConvertTo-Json -Depth 20

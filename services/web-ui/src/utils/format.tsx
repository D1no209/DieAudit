import { Alert } from "../ui";
import type { ArtifactRef, RuntimeReadiness, StorageSummary } from "../types";
import type { StatusTone } from "../ui";

export function statusTone(value?: string): StatusTone {
  if (!value) return "neutral";
  if (["completed", "confirmed", "ready", "pass", "success", "succeeded", "running"].includes(value)) return "success";
  if (["failed", "cancelled", "false_positive", "fail"].includes(value)) return "danger";
  if (["skipped", "completed_with_warnings", "needs_review", "warn", "warning"].includes(value)) return "warning";
  if (["queued", "starting", "open", "needs_agent", "agent_queued", "tracing", "validating"].includes(value)) return "processing";
  return "neutral";
}

export function severityColor(value: string) {
  return statusTone(value === "critical" || value === "high" ? "failed" : value === "medium" ? "warn" : value === "low" ? "queued" : value);
}

export function readinessColor(value: string) {
  return statusTone(value);
}

export function workerStatusTone(value: string) {
  if (value === "running") return "success";
  if (value === "idle" || value === "starting") return "processing";
  return "neutral";
}

export const workerStatusColor = workerStatusTone;

export function formatBytes(value?: number) {
  if (!value || value <= 0) return "-";
  if (value >= 1024 * 1024) return `${Math.round(value / (1024 * 1024))} MiB`;
  if (value >= 1024) return `${Math.round(value / 1024)} KiB`;
  return `${value} B`;
}

export function totalStorageBytes(summary?: StorageSummary) {
  if (!summary?.managed_prefixes) return undefined;
  return Object.values(summary.managed_prefixes).reduce((total, item) => total + (item.bytes || 0), 0);
}

export function renderReadinessDescription(item: NonNullable<RuntimeReadiness["checks"]>[number]) {
  const remediation = item.remediation || [];
  return (
    <div className="grid gap-3">
      {remediation.length > 0 && item.status !== "pass" ? (
        <Alert tone={item.status === "fail" ? "danger" : "warning"} title="Remediation">
          <ul className="mt-2 list-disc pl-5">
            {remediation.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Alert>
      ) : null}
      <pre>{JSON.stringify(item.detail || {}, null, 2)}</pre>
    </div>
  );
}

export function artifactUrl(artifact?: ArtifactRef, fallbackPath?: string) {
  const path = artifact?.download_url || (fallbackPath ? `/artifacts/download?path=${encodeURIComponent(fallbackPath)}` : "");
  if (!path) return "";
  if (path.startsWith("/gateway/")) return path;
  if (path.startsWith("/")) return `/gateway${path}`;
  return `/gateway/artifacts/download?path=${encodeURIComponent(path)}`;
}

export function artifactFileName(artifact?: ArtifactRef, fallbackPath?: string) {
  if (artifact?.name) return artifact.name;
  const source = artifact?.relative_path || fallbackPath || "artifact";
  const clean = source.split(/[\\/]/).filter(Boolean).pop();
  return clean || "artifact";
}

export function isActiveRun(auditStatus?: string, pipelineStatus?: string) {
  const activeStatuses = ["queued", "running", "validating", "cancelling"];
  return activeStatuses.includes(auditStatus || "") || activeStatuses.includes(pipelineStatus || "");
}

export function parseScopes(value?: string) {
  const scopes = (value || "admin")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
  return Array.from(new Set(scopes.length ? scopes : ["admin"]));
}

export function parseCsvList(value?: string) {
  const items = (value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return Array.from(new Set(items));
}

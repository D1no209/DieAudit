import { Alert, Space } from "antd";
import type { ArtifactRef, RuntimeReadiness, StorageSummary } from "../types";

export function severityColor(value: string) {
  if (value === "critical" || value === "high") return "red";
  if (value === "medium") return "orange";
  if (value === "low") return "blue";
  return "default";
}

export function readinessColor(value: string) {
  if (value === "fail") return "red";
  if (value === "warn") return "orange";
  return "green";
}

export function formatBytes(value?: number) {
  if (!value || value <= 0) {
    return "-";
  }
  if (value >= 1024 * 1024) {
    return `${Math.round(value / (1024 * 1024))} MiB`;
  }
  if (value >= 1024) {
    return `${Math.round(value / 1024)} KiB`;
  }
  return `${value} B`;
}

export function totalStorageBytes(summary?: StorageSummary) {
  if (!summary?.managed_prefixes) {
    return undefined;
  }
  return Object.values(summary.managed_prefixes).reduce((total, item) => total + (item.bytes || 0), 0);
}

export function renderReadinessDescription(item: NonNullable<RuntimeReadiness["checks"]>[number]) {
  const remediation = item.remediation || [];
  return (
    <Space direction="vertical" size={8} className="drawer-stack">
      {remediation.length > 0 && item.status !== "pass" ? (
        <Alert
          type={item.status === "fail" ? "error" : "warning"}
          showIcon
          message="Remediation"
          description={
            <ul className="readiness-remediation">
              {remediation.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          }
        />
      ) : null}
      <pre>{JSON.stringify(item.detail || {}, null, 2)}</pre>
    </Space>
  );
}

export function workerStatusColor(value: string) {
  if (value === "running") return "green";
  if (value === "idle" || value === "starting") return "blue";
  return "default";
}

export function artifactUrl(artifact?: ArtifactRef, fallbackPath?: string) {
  const path = artifact?.download_url || (fallbackPath ? `/artifacts/download?path=${encodeURIComponent(fallbackPath)}` : "");
  if (!path) {
    return "";
  }
  if (path.startsWith("/gateway/")) {
    return path;
  }
  if (path.startsWith("/")) {
    return `/gateway${path}`;
  }
  return `/gateway/artifacts/download?path=${encodeURIComponent(path)}`;
}

export function artifactFileName(artifact?: ArtifactRef, fallbackPath?: string) {
  if (artifact?.name) {
    return artifact.name;
  }
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

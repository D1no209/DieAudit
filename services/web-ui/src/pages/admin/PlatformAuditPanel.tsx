import { Trash2 } from "lucide-react";
import type { PlatformAuditEvent, RuntimePolicy, StorageSummary } from "../../types";
import { Badge, Button, DataTable, Panel, type DataColumn } from "../../ui";
import { formatBytes, totalStorageBytes } from "../../utils/format";

type Props = {
  loading: boolean;
  platformAuditColumns: DataColumn<PlatformAuditEvent>[];
  platformAuditEvents: PlatformAuditEvent[];
  runtimePolicy?: RuntimePolicy;
  storageSummary?: StorageSummary;
  onCleanupPlatformAuditEvents: () => void;
  onPreviewLocalStorageCleanup: () => void;
};

export function PlatformAuditPanel({
  loading,
  platformAuditColumns,
  platformAuditEvents,
  runtimePolicy,
  storageSummary,
  onCleanupPlatformAuditEvents,
  onPreviewLocalStorageCleanup,
}: Props) {
  return (
    <Panel>
      <div className="mb-4 flex flex-wrap gap-2">
        <Badge>retention: {runtimePolicy?.platform_audit_events?.retention_days ?? "-"}d</Badge>
        <Badge>max rows: {runtimePolicy?.platform_audit_events?.max_rows ?? "-"}</Badge>
        <Badge>runtime pkg: {runtimePolicy?.local_storage?.runtime_package_retention_days ?? "-"}d</Badge>
        <Badge>upload staging: {runtimePolicy?.local_storage?.upload_staging_retention_days ?? "-"}d</Badge>
        <Badge>unref workspaces: {runtimePolicy?.local_storage?.unreferenced_workspace_retention_days ?? "-"}d</Badge>
        <Badge>unref snapshots: {runtimePolicy?.local_storage?.unreferenced_snapshot_retention_days ?? "-"}d</Badge>
        <Badge>storage: {formatBytes(totalStorageBytes(storageSummary))}</Badge>
        <Badge>container memory: {runtimePolicy?.default_container?.memory ?? "-"}</Badge>
        <Badge>cpus: {runtimePolicy?.default_container?.cpus ?? "-"}</Badge>
        <Badge>max body: {formatBytes(runtimePolicy?.http_guards?.max_request_body_bytes)}</Badge>
        <Badge>max upload: {formatBytes(runtimePolicy?.http_guards?.max_upload_bytes)}</Badge>
        <Badge>zip files: {runtimePolicy?.workspace_import?.max_workspace_files ?? "-"}</Badge>
        <Badge>zip size: {formatBytes(runtimePolicy?.workspace_import?.max_workspace_uncompressed_bytes)}</Badge>
        <Badge>git schemes: {(runtimePolicy?.workspace_import?.allowed_git_url_schemes || []).join(",") || "-"}</Badge>
        <Badge>git hosts: {(runtimePolicy?.workspace_import?.allowed_git_hosts || []).join(",") || "public-only"}</Badge>
        <Badge>rate: {runtimePolicy?.http_guards?.rate_limit_per_minute ?? "-"} / {runtimePolicy?.http_guards?.rate_limit_window_seconds ?? "-"}s</Badge>
        <Button size="sm" icon={<Trash2 className="h-4 w-4" />} loading={loading} onClick={onCleanupPlatformAuditEvents}>清理审计事件</Button>
        <Button size="sm" icon={<Trash2 className="h-4 w-4" />} loading={loading} onClick={onPreviewLocalStorageCleanup}>预览存储清理</Button>
      </div>
      <DataTable getRowKey={(row) => row.id} columns={platformAuditColumns} data={platformAuditEvents} pagination={{ pageSize: 10 }} />
    </Panel>
  );
}

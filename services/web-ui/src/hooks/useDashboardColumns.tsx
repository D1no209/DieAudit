import { FileText, RefreshCw, Trash2 } from "lucide-react";
import type {
  AgentRun,
  ApiKeyRecord,
  ArtifactRef,
  ContainerRow,
  KnowledgeDocument,
  PlatformAuditEvent,
  Project,
  WorkerHeartbeat,
} from "../types";
import { Badge, Button, type DataColumn } from "../ui";
import { statusTone, workerStatusTone } from "../utils/format";

type Args = {
  onDeactivateManagedApiKey: (keyId: string) => void;
  onDeleteKnowledgeDocument: (documentId: string) => void;
  onOpenAgentEvents: (agentRunId: string) => void;
  onOpenArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onOpenContainerLogs: (row: ContainerRow) => void;
  onReindexKnowledgeDocument: (documentId: string) => void;
};

export function useDashboardColumns({
  onDeactivateManagedApiKey,
  onDeleteKnowledgeDocument,
  onOpenAgentEvents,
  onOpenArtifact,
  onOpenContainerLogs,
  onReindexKnowledgeDocument,
}: Args) {
  const projectColumns: DataColumn<Project>[] = [
    { title: "Project", dataIndex: "name" },
    { title: "Type", dataIndex: "source_type", render: (value) => <Badge>{String(value || "-")}</Badge> },
    { title: "Status", dataIndex: "status", render: (value) => <Badge tone={statusTone(String(value))}>{String(value || "-")}</Badge> },
  ];

  const agentColumns: DataColumn<AgentRun>[] = [
    { title: "Agent", dataIndex: "agent_name" },
    { title: "Status", dataIndex: "status", render: (value) => <Badge tone={statusTone(String(value))}>{String(value || "-")}</Badge> },
    { title: "Protocol", dataIndex: "protocol_kind" },
    { title: "Created", dataIndex: "created_at" },
    { title: "Events", render: (_, row) => <Button size="sm" onClick={() => onOpenAgentEvents(row.agent_run_id)}>查看</Button> },
  ];

  const containerColumns: DataColumn<ContainerRow>[] = [
    { title: "Role", render: (_, row) => <Badge>{row.role || row.Labels?.["dieaudit.role"] || "unknown"}</Badge> },
    { title: "Name", render: (_, row) => row.container_name || row.Names?.[0]?.replace("/", "") || "-" },
    { title: "Image", dataIndex: "Image" },
    { title: "State", render: (_, row) => <Badge tone={statusTone(row.State)}>{row.db_status || row.State}</Badge> },
    { title: "Exit", dataIndex: "exit_code", render: (value) => String(value ?? "-") },
    {
      title: "Logs",
      render: (_, row) => <Button size="sm" icon={<FileText className="h-4 w-4" />} onClick={() => onOpenContainerLogs(row)}>查看</Button>,
    },
  ];

  const platformAuditColumns: DataColumn<PlatformAuditEvent>[] = [
    { title: "Time", dataIndex: "created_at", width: 190 },
    { title: "Service", dataIndex: "service", width: 130, render: (value) => <Badge>{String(value || "-")}</Badge> },
    { title: "Method", dataIndex: "method", width: 90 },
    { title: "Path", dataIndex: "path" },
    {
      title: "Status",
      dataIndex: "status_code",
      width: 90,
      render: (value) => <Badge tone={Number(value) >= 500 ? "danger" : Number(value) >= 400 ? "warning" : "success"}>{String(value || "-")}</Badge>,
    },
    {
      title: "Auth",
      dataIndex: "auth_result",
      width: 130,
      render: (value) => <Badge tone={value === "failed" ? "danger" : value === "success" ? "success" : "neutral"}>{String(value || "-")}</Badge>,
    },
    { title: "Client", dataIndex: "client_host", width: 140, render: (value) => String(value || "-") },
    { title: "Duration", width: 110, render: (_, row) => `${row.metadata?.duration_ms ?? "-"} ms` },
    { title: "Request ID", dataIndex: "request_id", width: 260 },
  ];

  const workerColumns: DataColumn<WorkerHeartbeat>[] = [
    { title: "Worker", dataIndex: "worker_id" },
    { title: "Service", dataIndex: "service_name", render: (value) => <Badge>{String(value || "-")}</Badge> },
    { title: "Status", dataIndex: "status", render: (value) => <Badge tone={workerStatusTone(String(value))}>{String(value || "-")}</Badge> },
    { title: "Current Run", dataIndex: "current_audit_run_id", render: (value) => String(value || "-") },
    { title: "Age", dataIndex: "age_seconds", render: (value) => `${Math.round(Number(value || 0))}s` },
    { title: "Last Seen", dataIndex: "last_seen_at" },
  ];

  const apiKeyColumns: DataColumn<ApiKeyRecord>[] = [
    { title: "Name", dataIndex: "name" },
    { title: "Status", dataIndex: "status", render: (value) => <Badge tone={value === "active" ? "success" : "neutral"}>{String(value || "-")}</Badge> },
    { title: "Scopes", dataIndex: "scopes", render: (value) => <span className="flex flex-wrap gap-1">{(value as string[]).map((item) => <Badge key={item}>{item}</Badge>)}</span> },
    {
      title: "Limits",
      render: (_, row) => {
        const projectIds = metadataList(row.metadata?.project_ids);
        const auditRunIds = metadataList(row.metadata?.audit_run_ids);
        if (!projectIds.length && !auditRunIds.length) {
          return <Badge>global</Badge>;
        }
        return (
          <span className="flex flex-wrap gap-1">
            {projectIds.map((item) => <Badge key={`project-${item}`}>project:{item}</Badge>)}
            {auditRunIds.map((item) => <Badge key={`audit-${item}`}>run:{item}</Badge>)}
          </span>
        );
      },
    },
    { title: "Last Used", dataIndex: "last_used_at", render: (value) => String(value || "-") },
    { title: "Created", dataIndex: "created_at" },
    {
      title: "Action",
      render: (_, row) => (
        <Button size="sm" variant="danger" disabled={row.status !== "active"} onClick={() => onDeactivateManagedApiKey(row.key_id)}>
          禁用
        </Button>
      ),
    },
  ];

  const knowledgeColumns: DataColumn<KnowledgeDocument>[] = [
    { title: "Title", dataIndex: "title" },
    { title: "Source", dataIndex: "source_name" },
    { title: "Scope", dataIndex: "scope", render: (value, row) => <Badge>{String(value)}{row.project_id ? `:${row.project_id}` : ""}</Badge> },
    { title: "Status", dataIndex: "status", render: (value) => <Badge tone={value === "indexed" ? "success" : "danger"}>{String(value || "-")}</Badge> },
    { title: "Chunks", dataIndex: "chunk_count" },
    { title: "Created", dataIndex: "created_at" },
    {
      title: "Action",
      render: (_, row) => (
        <span className="flex flex-wrap gap-2">
          <Button size="sm" icon={<RefreshCw className="h-4 w-4" />} onClick={() => onReindexKnowledgeDocument(row.document_id)}>重建</Button>
          <Button size="sm" icon={<FileText className="h-4 w-4" />} disabled={!row.artifact} onClick={() => onOpenArtifact(row.artifact)}>下载</Button>
          <Button
            size="sm"
            variant="danger"
            icon={<Trash2 className="h-4 w-4" />}
            onClick={() => {
              if (window.confirm("删除知识库文档？")) onDeleteKnowledgeDocument(row.document_id);
            }}
          >
            删除
          </Button>
        </span>
      ),
    },
  ];

  return { agentColumns, apiKeyColumns, containerColumns, knowledgeColumns, platformAuditColumns, projectColumns, workerColumns };
}

export type DashboardColumns = ReturnType<typeof useDashboardColumns>;

function metadataList(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === "string") {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

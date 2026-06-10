import { DeleteOutlined, FileTextOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Popconfirm, Space, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
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
import { workerStatusColor } from "../utils/format";

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
  const projectColumns: ColumnsType<Project> = [
    { title: "Project", dataIndex: "name" },
    { title: "Type", dataIndex: "source_type", render: (value) => <Tag>{value}</Tag> },
    { title: "Status", dataIndex: "status", render: (value) => <Tag color={value === "ready" ? "green" : "blue"}>{value}</Tag> },
  ];

  const agentColumns: ColumnsType<AgentRun> = [
    { title: "Agent", dataIndex: "agent_name" },
    { title: "Status", dataIndex: "status", render: (value) => <Tag color={value === "completed" ? "green" : "blue"}>{value}</Tag> },
    { title: "Protocol", dataIndex: "protocol_kind" },
    { title: "Created", dataIndex: "created_at" },
    { title: "Events", render: (_, row) => <Button size="small" onClick={() => onOpenAgentEvents(row.agent_run_id)}>查看</Button> },
  ];

  const containerColumns: ColumnsType<ContainerRow> = [
    { title: "Role", render: (_, row) => <Tag>{row.role || row.Labels?.["dieaudit.role"] || "unknown"}</Tag> },
    { title: "Name", render: (_, row) => row.container_name || row.Names?.[0]?.replace("/", "") || "-" },
    { title: "Image", dataIndex: "Image" },
    { title: "State", render: (_, row) => <Tag color={row.State === "running" ? "green" : row.State === "removed" ? "default" : "blue"}>{row.db_status || row.State}</Tag> },
    { title: "Exit", dataIndex: "exit_code", render: (value) => value ?? "-" },
    { title: "Logs", render: (_, row) => <Button size="small" icon={<FileTextOutlined />} onClick={() => onOpenContainerLogs(row)}>查看</Button> },
  ];

  const platformAuditColumns: ColumnsType<PlatformAuditEvent> = [
    { title: "Time", dataIndex: "created_at", width: 190 },
    { title: "Service", dataIndex: "service", width: 130, render: (value) => <Tag>{value}</Tag> },
    { title: "Method", dataIndex: "method", width: 90 },
    { title: "Path", dataIndex: "path", ellipsis: true },
    {
      title: "Status",
      dataIndex: "status_code",
      width: 90,
      render: (value) => <Tag color={value >= 500 ? "red" : value >= 400 ? "orange" : "green"}>{value}</Tag>,
    },
    {
      title: "Auth",
      dataIndex: "auth_result",
      width: 130,
      render: (value) => <Tag color={value === "failed" ? "red" : value === "success" ? "green" : "default"}>{value}</Tag>,
    },
    { title: "Client", dataIndex: "client_host", width: 140, render: (value) => value || "-" },
    {
      title: "Duration",
      width: 110,
      render: (_, row) => `${row.metadata?.duration_ms ?? "-"} ms`,
    },
    { title: "Request ID", dataIndex: "request_id", width: 260, ellipsis: true },
  ];

  const workerColumns: ColumnsType<WorkerHeartbeat> = [
    { title: "Worker", dataIndex: "worker_id", ellipsis: true },
    { title: "Service", dataIndex: "service_name", render: (value) => <Tag>{value}</Tag> },
    { title: "Status", dataIndex: "status", render: (value) => <Tag color={workerStatusColor(value)}>{value}</Tag> },
    { title: "Current Run", dataIndex: "current_audit_run_id", render: (value) => value || "-" },
    { title: "Age", dataIndex: "age_seconds", render: (value) => `${Math.round(Number(value || 0))}s` },
    { title: "Last Seen", dataIndex: "last_seen_at" },
  ];

  const apiKeyColumns: ColumnsType<ApiKeyRecord> = [
    { title: "Name", dataIndex: "name" },
    { title: "Status", dataIndex: "status", render: (value) => <Tag color={value === "active" ? "green" : "default"}>{value}</Tag> },
    { title: "Scopes", dataIndex: "scopes", render: (value: string[]) => <Space wrap>{value.map((item) => <Tag key={item}>{item}</Tag>)}</Space> },
    {
      title: "Limits",
      render: (_, row) => {
        const projectIds = metadataList(row.metadata?.project_ids);
        const auditRunIds = metadataList(row.metadata?.audit_run_ids);
        if (!projectIds.length && !auditRunIds.length) {
          return <Tag>global</Tag>;
        }
        return (
          <Space wrap>
            {projectIds.map((item) => <Tag key={`project-${item}`}>project:{item}</Tag>)}
            {auditRunIds.map((item) => <Tag key={`audit-${item}`}>run:{item}</Tag>)}
          </Space>
        );
      },
    },
    { title: "Last Used", dataIndex: "last_used_at", render: (value) => value || "-" },
    { title: "Created", dataIndex: "created_at" },
    {
      title: "Action",
      render: (_, row) => (
        <Button size="small" danger disabled={row.status !== "active"} onClick={() => onDeactivateManagedApiKey(row.key_id)}>
          禁用
        </Button>
      ),
    },
  ];

  const knowledgeColumns: ColumnsType<KnowledgeDocument> = [
    { title: "Title", dataIndex: "title" },
    { title: "Source", dataIndex: "source_name", ellipsis: true },
    { title: "Scope", dataIndex: "scope", render: (value, row) => <Tag>{value}{row.project_id ? `:${row.project_id}` : ""}</Tag> },
    { title: "Status", dataIndex: "status", render: (value) => <Tag color={value === "indexed" ? "green" : "red"}>{value}</Tag> },
    { title: "Chunks", dataIndex: "chunk_count" },
    { title: "Created", dataIndex: "created_at" },
    {
      title: "Action",
      render: (_, row) => (
        <Space>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => onReindexKnowledgeDocument(row.document_id)}>
            重建
          </Button>
          <Button size="small" icon={<FileTextOutlined />} disabled={!row.artifact} onClick={() => onOpenArtifact(row.artifact)}>
            下载
          </Button>
          <Popconfirm title="删除知识库文档？" okText="删除" cancelText="取消" onConfirm={() => onDeleteKnowledgeDocument(row.document_id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return {
    agentColumns,
    apiKeyColumns,
    containerColumns,
    knowledgeColumns,
    platformAuditColumns,
    projectColumns,
    workerColumns,
  };
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

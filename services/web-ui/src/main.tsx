import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ApiOutlined,
  BugOutlined,
  CloudServerOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Collapse,
  ConfigProvider,
  Descriptions,
  Drawer,
  Flex,
  Form,
  Input,
  Layout,
  List,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
  theme,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { UploadFile } from "antd/es/upload/interface";
import "antd/dist/reset.css";
import "./styles.css";

const { Header, Content } = Layout;
const { Title, Text, Paragraph } = Typography;
const API_KEY_STORAGE_KEY = "dieaudit.apiKey";
const API_KEY_HEADER = "X-DieAudit-Api-Key";

type Project = {
  project_id: string;
  name: string;
  source_type: string;
  status: string;
  metadata?: Record<string, unknown>;
};

type AuditRun = {
  audit_run_id: string;
  project_id: string;
  snapshot_id?: string;
  status: string;
  created_at: string;
};

type AgentRun = {
  agent_run_id: string;
  agent_name: string;
  status: string;
  protocol_kind: string;
  created_at: string;
};

type Finding = {
  finding_id: string;
  title: string;
  severity: string;
  status: string;
  file_path?: string;
  line_start?: number;
  line_end?: number;
  rule_id?: string;
  source: string;
  description?: string;
  raw?: Record<string, unknown>;
};

type FindingDetail = {
  finding: Finding;
  evidence: Array<Record<string, unknown>>;
  validation_attempts: Array<Record<string, unknown>>;
};

type ReportArtifact = {
  report_id: string;
  kind: string;
  path: string;
  summary: Record<string, unknown>;
  created_at: string;
};

type AuditRunEvent = {
  id: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

type PipelineStatus = {
  current?: {
    stage?: string;
    status?: string;
    error?: string;
  };
  runtime_control?: {
    cancel_requested?: boolean;
    cancel_reason?: string;
    cancel_requested_at?: string;
  };
  counts?: {
    findings?: Record<string, number>;
    validation_attempts?: Record<string, number>;
    reports?: number;
  };
  events: AuditRunEvent[];
};

type ManagedRuntime = {
  summary?: {
    container_count?: number;
    network_count?: number;
    run_count?: number;
    expired_run_count?: number;
  };
};

type RuntimePolicy = {
  default_container?: {
    memory?: string;
    cpus?: number;
    pids_limit?: number;
    tmpfs?: string;
  };
  platform_audit_events?: {
    retention_days?: number;
    max_rows?: number;
  };
};

type SandboxCapabilities = {
  ok?: boolean;
  docker_available?: boolean;
  configured_gvisor?: boolean;
  allow_runc_sandbox?: boolean;
  gvisor_available?: boolean;
  strong_isolation_available?: boolean;
  sandbox_execution_available?: boolean;
  requested_runtime?: string;
  reason?: string;
  warnings?: string[];
};

type AuthStatus = {
  enabled?: boolean;
  api_key_header?: string;
  public_metrics?: boolean;
  service?: string;
};

type PlatformAuditEvent = {
  id: number;
  service: string;
  method: string;
  path: string;
  status_code: number;
  client_host?: string;
  user_agent?: string;
  auth_enabled: boolean;
  auth_result: string;
  request_id?: string;
  metadata?: Record<string, unknown>;
  created_at: string;
};

type ContainerRow = {
  Id: string;
  Image: string;
  Names: string[];
  State: string;
  Status: string;
  Labels: Record<string, string>;
  role?: string;
  db_status?: string;
  exit_code?: number;
  log_artifact?: string;
  container_name?: string;
};

async function readJson(path: string, options?: RequestInit) {
  const response = await fetch(path, withAuth(options));
  const text = await response.text();
  if (!response.ok) {
    throw new Error(text || response.statusText);
  }
  return text ? JSON.parse(text) : {};
}

function withAuth(options?: RequestInit): RequestInit {
  const headers = new Headers(options?.headers);
  const apiKey = window.localStorage.getItem(API_KEY_STORAGE_KEY);
  if (apiKey) {
    headers.set(API_KEY_HEADER, apiKey);
  }
  return { ...options, headers };
}

function App() {
  const [apiHealth, setApiHealth] = useState<any>();
  const [authStatus, setAuthStatus] = useState<AuthStatus>();
  const [dockerHealth, setDockerHealth] = useState<any>();
  const [managedRuntime, setManagedRuntime] = useState<ManagedRuntime>();
  const [runtimePolicy, setRuntimePolicy] = useState<RuntimePolicy>();
  const [sandboxCapabilities, setSandboxCapabilities] = useState<SandboxCapabilities>();
  const [platformAuditEvents, setPlatformAuditEvents] = useState<PlatformAuditEvent[]>([]);
  const [apiKey, setApiKey] = useState(() => window.localStorage.getItem(API_KEY_STORAGE_KEY) || "");
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [auditRun, setAuditRun] = useState<AuditRun>();
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [containers, setContainers] = useState<ContainerRow[]>([]);
  const [reports, setReports] = useState<ReportArtifact[]>([]);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>();
  const [selectedFinding, setSelectedFinding] = useState<FindingDetail>();
  const [agentEvents, setAgentEvents] = useState<Array<Record<string, unknown>>>();
  const [containerLogs, setContainerLogs] = useState<{ title: string; body: string }>();
  const [sandboxTarget, setSandboxTarget] = useState<{ network: string; target_url: string }>();
  const [lastResponse, setLastResponse] = useState<any>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [zipFiles, setZipFiles] = useState<UploadFile[]>([]);
  const [gitForm] = Form.useForm();
  const [zipForm] = Form.useForm();

  const selectedProject = useMemo(
    () => projects.find((project) => project.project_id === selectedProjectId),
    [projects, selectedProjectId],
  );

  async function refresh() {
    setError(undefined);
    try {
      const [api, auth] = await Promise.all([
        readJson("/api/health"),
        readJson("/api/auth/status"),
      ]);
      setApiHealth(api);
      setAuthStatus(auth);
      const [docker, projectRows] = await Promise.all([
        readJson("/gateway/runtime/docker/health"),
        readJson("/gateway/projects"),
      ]);
      setDockerHealth(docker);
      readJson("/gateway/runtime/managed").then(setManagedRuntime).catch(() => setManagedRuntime(undefined));
      readJson("/gateway/runtime/policy").then(setRuntimePolicy).catch(() => setRuntimePolicy(undefined));
      readJson("/gateway/runtime/sandbox/capabilities").then(setSandboxCapabilities).catch(() => setSandboxCapabilities(undefined));
      readJson("/gateway/platform/audit-events?limit=100").then(setPlatformAuditEvents).catch(() => setPlatformAuditEvents([]));
      setProjects(projectRows);
      if (!selectedProjectId && projectRows.length > 0) {
        setSelectedProjectId(projectRows[0].project_id);
      }
      if (auditRun) {
        await refreshAuditRun(auditRun.audit_run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function refreshAuditRun(auditRunId: string) {
    const [run, agents, findingRows, containerRows, reportRows, pipeline] = await Promise.all([
      readJson(`/gateway/audit-runs/${auditRunId}`),
      readJson(`/gateway/audit-runs/${auditRunId}/agent-runs`),
      readJson(`/gateway/audit-runs/${auditRunId}/findings`),
      readJson(`/gateway/audit-runs/${auditRunId}/containers`),
      readJson(`/gateway/audit-runs/${auditRunId}/reports`),
      readJson(`/gateway/audit-runs/${auditRunId}/pipeline-status`),
    ]);
    setAuditRun(run);
    setAgentRuns(agents);
    setFindings(findingRows);
    setContainers(containerRows);
    setReports(reportRows);
    setPipelineStatus(pipeline);
  }

  async function createGitProject(values: { name: string; git_url: string; ref?: string }) {
    await runAction(async () => {
      const result = await readJson("/gateway/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      setLastResponse(result);
      setSelectedProjectId(result.project.project_id);
      gitForm.resetFields();
      await refresh();
    });
  }

  async function uploadZipProject(values: { name: string }) {
    if (!zipFiles[0]?.originFileObj) {
      message.error("请选择 zip 文件");
      return;
    }
    await runAction(async () => {
      const formData = new FormData();
      formData.append("name", values.name);
      formData.append("file", zipFiles[0].originFileObj);
      const result = await readJson("/gateway/projects/upload-zip", { method: "POST", body: formData });
      setLastResponse(result);
      setSelectedProjectId(result.project.project_id);
      zipForm.resetFields();
      setZipFiles([]);
      await refresh();
    });
  }

  async function startAudit() {
    if (!selectedProjectId) {
      message.error("请选择项目");
      return;
    }
    await runAction(async () => {
      const result = await readJson(`/gateway/projects/${selectedProjectId}/audit-runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_name: "opencode-orchestrator",
          allow_external_network: true,
          input_payload: {
            goal: "Run an initial security audit. Inspect the mounted source and report vulnerability candidates with file paths.",
          },
        }),
      });
      setLastResponse(result);
      await refreshAuditRun(result.audit_run.audit_run_id);
    });
  }

  async function runSca() {
    if (!auditRun) {
      message.error("请先启动 AuditRun");
      return;
    }
    await runAction(async () => {
      const result = await readJson(`/gateway/audit-runs/${auditRun.audit_run_id}/sca`, { method: "POST" });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function runPipeline() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    await runAction(async () => {
      const result = await readJson(`/gateway/audit-runs/${auditRun.audit_run_id}/run-pipeline`, { method: "POST" });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function runJudge() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    await runAction(async () => {
      const result = await readJson(`/gateway/audit-runs/${auditRun.audit_run_id}/judge`, { method: "POST" });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function generateReport() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    await runAction(async () => {
      const result = await readJson(`/gateway/audit-runs/${auditRun.audit_run_id}/report`, { method: "POST" });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function runPocSmoke() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    await runAction(async () => {
      const result = await readJson(`/gateway/audit-runs/${auditRun.audit_run_id}/sandbox/poc`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image: "python:3.12-slim",
          command: [
            "python",
            "-c",
            "import os, json; print('dieaudit poc smoke'); print(json.dumps(os.listdir('/workspace')[:20] if os.path.exists('/workspace') else []))",
          ],
          allow_external_network: false,
          timeout_seconds: 120,
          allow_weak_isolation: true,
        }),
      });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
      const managed = await readJson("/gateway/runtime/managed");
      setManagedRuntime(managed);
    });
  }

  async function startSandboxService() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    await runAction(async () => {
      const result = await readJson(`/gateway/audit-runs/${auditRun.audit_run_id}/sandbox/service`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image: "python:3.12-slim",
          command: ["python", "-m", "http.server", "8080", "--directory", "/workspace"],
          service_name: "target",
          port: 8080,
          allow_external_network: false,
          retain_runtime_on_failure: true,
          startup_timeout_seconds: 30,
          allow_weak_isolation: true,
        }),
      });
      setSandboxTarget({ network: result.network, target_url: result.target_url });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
      const managed = await readJson("/gateway/runtime/managed");
      setManagedRuntime(managed);
    });
  }

  async function runSandboxTargetPoc() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    if (!sandboxTarget) {
      message.error("请先启动 Sandbox Service");
      return;
    }
    await runAction(async () => {
      const result = await readJson(`/gateway/audit-runs/${auditRun.audit_run_id}/sandbox/poc`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image: "python:3.12-slim",
          command: [
            "python",
            "-c",
            "import os, urllib.request; url=os.environ['TARGET_URL']; r=urllib.request.urlopen(url, timeout=5); print(url); print(r.status); print(r.read(120).decode('utf-8', 'replace'))",
          ],
          network_name: sandboxTarget.network,
          target_url: sandboxTarget.target_url,
          allow_external_network: false,
          timeout_seconds: 120,
          expected_exit_code: 0,
          allow_weak_isolation: true,
        }),
      });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
      const managed = await readJson("/gateway/runtime/managed");
      setManagedRuntime(managed);
    });
  }

  function downloadReport(reportId: string) {
    window.open(`/gateway/reports/${reportId}/download`, "_blank", "noopener,noreferrer");
  }

  async function openFinding(findingId: string) {
    await runAction(async () => {
      const result = await readJson(`/gateway/findings/${findingId}`);
      setSelectedFinding(result);
    });
  }

  async function runFindingPoc() {
    if (!selectedFinding || !auditRun) {
      return;
    }
    const findingId = selectedFinding.finding.finding_id;
    await runAction(async () => {
      const result = await readJson(`/gateway/findings/${findingId}/poc`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image: "python:3.12-slim",
          command: [
            "python",
            "-c",
            "import os, json; print('dieaudit finding poc smoke'); print(json.dumps({'workspace': os.listdir('/workspace')[:20] if os.path.exists('/workspace') else [], 'artifact_dir': os.environ.get('ARTIFACT_DIR')}))",
          ],
          allow_external_network: false,
          timeout_seconds: 120,
          expected_exit_code: 0,
          allow_weak_isolation: true,
        }),
      });
      setLastResponse(result);
      setSelectedFinding(result.finding);
      await refreshAuditRun(auditRun.audit_run_id);
      const managed = await readJson("/gateway/runtime/managed");
      setManagedRuntime(managed);
    });
  }

  async function openAgentEvents(agentRunId: string) {
    if (!auditRun) {
      return;
    }
    await runAction(async () => {
      const result = await readJson(`/gateway/audit-runs/${auditRun.audit_run_id}/agent-runs/${agentRunId}/events`);
      setAgentEvents(result);
    });
  }

  async function openContainerLogs(row: ContainerRow) {
    if (!auditRun) {
      return;
    }
    await runAction(async () => {
      const response = await fetch(
        `/gateway/audit-runs/${auditRun.audit_run_id}/containers/${encodeURIComponent(row.Id)}/logs`,
        withAuth(),
      );
      const text = await response.text();
      if (!response.ok) {
        throw new Error(text || response.statusText);
      }
      setContainerLogs({ title: row.container_name || row.Names?.[0]?.replace("/", "") || row.Id.slice(0, 12), body: text });
    });
  }

  async function cleanup() {
    if (!auditRun) {
      return;
    }
    await runAction(async () => {
      const result = await readJson(`/gateway/audit-runs/${auditRun.audit_run_id}/cleanup`, { method: "POST" });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function cancelAuditRun() {
    if (!auditRun) {
      return;
    }
    await runAction(async () => {
      const result = await readJson(`/gateway/audit-runs/${auditRun.audit_run_id}/cancel`, { method: "POST" });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function cleanupExpiredRuntime() {
    await runAction(async () => {
      const result = await readJson("/gateway/runtime/cleanup-expired", { method: "POST" });
      setLastResponse(result);
      const managed = await readJson("/gateway/runtime/managed");
      setManagedRuntime(managed);
      if (auditRun) {
        await refreshAuditRun(auditRun.audit_run_id);
      }
    });
  }

  async function cleanupPlatformAuditEvents() {
    await runAction(async () => {
      const result = await readJson("/gateway/platform/audit-events", { method: "DELETE" });
      setLastResponse(result);
      const rows = await readJson("/gateway/platform/audit-events?limit=100");
      setPlatformAuditEvents(rows);
    });
  }

  function saveApiKey() {
    const normalized = apiKey.trim();
    if (normalized) {
      window.localStorage.setItem(API_KEY_STORAGE_KEY, normalized);
    } else {
      window.localStorage.removeItem(API_KEY_STORAGE_KEY);
    }
    refresh();
  }

  async function runAction(action: () => Promise<void>) {
    setLoading(true);
    setError(undefined);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!auditRun?.audit_run_id || !isActiveRun(auditRun.status, pipelineStatus?.current?.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      refreshAuditRun(auditRun.audit_run_id).catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
      });
    }, 4000);
    return () => window.clearInterval(timer);
  }, [auditRun?.audit_run_id, auditRun?.status, pipelineStatus?.current?.status]);

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
    { title: "Events", render: (_, row) => <Button size="small" onClick={() => openAgentEvents(row.agent_run_id)}>查看</Button> },
  ];

  const findingColumns: ColumnsType<Finding> = [
    { title: "Title", dataIndex: "title" },
    { title: "Severity", dataIndex: "severity", render: (value) => <Tag color={severityColor(value)}>{value}</Tag> },
    { title: "Status", dataIndex: "status" },
    { title: "Path", dataIndex: "file_path", render: (value) => value || "-" },
    { title: "Rule", dataIndex: "rule_id", render: (value) => value || "-" },
    { title: "Source", dataIndex: "source" },
    { title: "Detail", render: (_, row) => <Button size="small" onClick={() => openFinding(row.finding_id)}>研判</Button> },
  ];

  const containerColumns: ColumnsType<ContainerRow> = [
    { title: "Role", render: (_, row) => <Tag>{row.role || row.Labels?.["dieaudit.role"] || "unknown"}</Tag> },
    { title: "Name", render: (_, row) => row.container_name || row.Names?.[0]?.replace("/", "") || "-" },
    { title: "Image", dataIndex: "Image" },
    { title: "State", render: (_, row) => <Tag color={row.State === "running" ? "green" : row.State === "removed" ? "default" : "blue"}>{row.db_status || row.State}</Tag> },
    { title: "Exit", dataIndex: "exit_code", render: (value) => value ?? "-" },
    { title: "Logs", render: (_, row) => <Button size="small" icon={<FileTextOutlined />} onClick={() => openContainerLogs(row)}>查看</Button> },
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

  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm }}>
      <Layout className="app-shell">
        <Header className="app-header">
          <Flex align="center" justify="space-between" gap={16}>
            <Space>
              <BugOutlined className="brand-icon" />
              <div>
                <Title level={3} className="brand-title">DieAudit</Title>
                <Text className="brand-subtitle">多 Agent 代码审计运行台</Text>
              </div>
            </Space>
            <Space wrap>
              <Input.Password
                className="api-key-input"
                placeholder="API Key"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                onPressEnter={saveApiKey}
              />
              <Button onClick={saveApiKey}>保存 Key</Button>
              <Button icon={<ReloadOutlined />} onClick={refresh}>刷新</Button>
              <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={startAudit}>启动审计</Button>
              <Button icon={<PlayCircleOutlined />} loading={loading} onClick={runPipeline}>一键闭环</Button>
              <Button icon={<SafetyCertificateOutlined />} loading={loading} onClick={runSca}>SCA 扫描</Button>
              <Button icon={<SafetyCertificateOutlined />} loading={loading} onClick={runJudge}>研判</Button>
              <Button icon={<CloudServerOutlined />} loading={loading} onClick={startSandboxService}>Sandbox Service</Button>
              <Button icon={<SafetyCertificateOutlined />} loading={loading} disabled={!sandboxTarget} onClick={runSandboxTargetPoc}>Target PoC</Button>
              <Button icon={<SafetyCertificateOutlined />} loading={loading} onClick={runPocSmoke}>PoC Smoke</Button>
              <Button icon={<FileTextOutlined />} loading={loading} onClick={generateReport}>报告</Button>
              <Button danger icon={<StopOutlined />} loading={loading} disabled={!auditRun || !isActiveRun(auditRun.status, pipelineStatus?.current?.status)} onClick={cancelAuditRun}>取消</Button>
              <Button icon={<DeleteOutlined />} loading={loading} onClick={cleanupExpiredRuntime}>清理过期</Button>
              <Button danger icon={<DeleteOutlined />} loading={loading} onClick={cleanup}>清理运行时</Button>
            </Space>
          </Flex>
        </Header>
        <Content className="app-content">
          {error && <Alert type="error" showIcon message="运行错误" description={error} className="section" />}
          <div className="stats-grid section">
            <Card><Statistic title="Web API" value={apiHealth?.ok ? "Healthy" : "Unknown"} prefix={<ApiOutlined />} /></Card>
            <Card>
              <Statistic title="API Auth" value={authStatus?.enabled ? "Enabled" : "Disabled"} prefix={<SafetyCertificateOutlined />} />
              {!authStatus?.enabled && <Text type="danger">Set DIEAUDIT_API_KEY before production use.</Text>}
            </Card>
            <Card><Statistic title="Docker Runtime" value={dockerHealth?.ok ? "Ready" : "Unknown"} prefix={<CloudServerOutlined />} /></Card>
            <Card><Statistic title="Projects" value={projects.length} prefix={<FolderOpenOutlined />} /></Card>
            <Card><Statistic title="Findings" value={findings.length} prefix={<BugOutlined />} /></Card>
            <Card><Statistic title="Runtime Containers" value={managedRuntime?.summary?.container_count ?? 0} prefix={<CloudServerOutlined />} /></Card>
            <Card>
              <Statistic
                title={`Sandbox ${sandboxCapabilities?.requested_runtime || ""}`}
                value={sandboxCapabilities?.sandbox_execution_available ? "Ready" : "Unavailable"}
                prefix={<SafetyCertificateOutlined />}
              />
              {sandboxCapabilities?.requested_runtime === "runc" && !sandboxCapabilities?.strong_isolation_available && (
                <Text type={sandboxCapabilities?.allow_runc_sandbox ? "warning" : "danger"}>
                  {sandboxCapabilities?.allow_runc_sandbox ? "Weak runc isolation enabled" : "Strong isolation unavailable"}
                </Text>
              )}
              {sandboxCapabilities?.warnings?.[0] && <Text type="secondary">{sandboxCapabilities.warnings[0]}</Text>}
            </Card>
          </div>
          <div className="workspace-grid section">
            <Card title="Projects">
              <Tabs
                items={[
                  {
                    key: "git",
                    label: "Git",
                    children: (
                      <Form form={gitForm} layout="vertical" onFinish={createGitProject}>
                        <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                          <Input />
                        </Form.Item>
                        <Form.Item name="git_url" label="Git URL" rules={[{ required: true }]}>
                          <Input />
                        </Form.Item>
                        <Form.Item name="ref" label="Ref">
                          <Input />
                        </Form.Item>
                        <Button htmlType="submit" type="primary" loading={loading}>导入 Git</Button>
                      </Form>
                    ),
                  },
                  {
                    key: "zip",
                    label: "Zip",
                    children: (
                      <Form form={zipForm} layout="vertical" onFinish={uploadZipProject}>
                        <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                          <Input />
                        </Form.Item>
                        <Upload beforeUpload={() => false} maxCount={1} fileList={zipFiles} onChange={({ fileList }) => setZipFiles(fileList)}>
                          <Button>选择 zip</Button>
                        </Upload>
                        <Button className="form-action" htmlType="submit" type="primary" loading={loading}>上传 Zip</Button>
                      </Form>
                    ),
                  },
                ]}
              />
              <Table
                rowKey="project_id"
                size="small"
                columns={projectColumns}
                dataSource={projects}
                pagination={false}
                rowSelection={{ type: "radio", selectedRowKeys: selectedProjectId ? [selectedProjectId] : [], onChange: ([key]) => setSelectedProjectId(String(key)) }}
              />
            </Card>
            <Card title="Current AuditRun">
              <Paragraph>
                <Text strong>Project: </Text>{selectedProject?.name || "-"}
              </Paragraph>
              <Paragraph>
                <Text strong>AuditRun: </Text>{auditRun?.audit_run_id || "-"}
              </Paragraph>
              <Paragraph>
                <Text strong>Status: </Text>{auditRun?.status || "-"}
              </Paragraph>
              <Paragraph>
                <Text strong>Pipeline: </Text>
                <Tag color={pipelineStatus?.current?.status === "failed" ? "red" : pipelineStatus?.current?.status === "completed" ? "green" : "blue"}>
                  {pipelineStatus?.current?.stage || "-"} / {pipelineStatus?.current?.status || "-"}
                </Tag>
              </Paragraph>
              {pipelineStatus?.current?.error && <Alert type="error" showIcon message={pipelineStatus.current.error} />}
              {pipelineStatus?.runtime_control?.cancel_requested && (
                <Alert
                  type="warning"
                  showIcon
                  message="取消已请求"
                  description={`${pipelineStatus.runtime_control.cancel_reason || "cancel_requested"} ${pipelineStatus.runtime_control.cancel_requested_at || ""}`}
                />
              )}
              <pre>{JSON.stringify(lastResponse || { hint: "Import a project, start an audit, then run SCA." }, null, 2)}</pre>
            </Card>
          </div>
          <Tabs
            className="section"
            items={[
              { key: "agents", label: "AgentRuns", children: <Card><Table rowKey="agent_run_id" columns={agentColumns} dataSource={agentRuns} pagination={false} /></Card> },
              {
                key: "pipeline",
                label: "Pipeline",
                children: (
                  <Card>
                    <Space direction="vertical" size={16} className="drawer-stack">
                      <Space wrap>
                        {Object.entries(pipelineStatus?.counts?.findings || {}).map(([status, count]) => (
                          <Tag key={status}>{status}: {count}</Tag>
                        ))}
                        {Object.entries(pipelineStatus?.counts?.validation_attempts || {}).map(([status, count]) => (
                          <Tag key={`attempt-${status}`}>attempt {status}: {count}</Tag>
                        ))}
                        <Tag>reports: {pipelineStatus?.counts?.reports ?? 0}</Tag>
                      </Space>
                      <List
                        dataSource={pipelineStatus?.events || []}
                        renderItem={(item) => (
                          <List.Item>
                            <List.Item.Meta
                              title={<Space><Tag>{item.event_type}</Tag><Text>{item.created_at}</Text></Space>}
                              description={<pre>{JSON.stringify(item.payload || {}, null, 2)}</pre>}
                            />
                          </List.Item>
                        )}
                      />
                    </Space>
                  </Card>
                ),
              },
              { key: "findings", label: "Findings", children: <Card><Table rowKey="finding_id" columns={findingColumns} dataSource={findings} pagination={{ pageSize: 8 }} /></Card> },
              { key: "containers", label: "Containers", children: <Card><Table rowKey="Id" columns={containerColumns} dataSource={containers} pagination={false} /></Card> },
              {
                key: "platform-audit",
                label: "Platform Audit",
                children: (
                  <Card>
                    <Space wrap className="table-toolbar">
                      <Tag>retention: {runtimePolicy?.platform_audit_events?.retention_days ?? "-"}d</Tag>
                      <Tag>max rows: {runtimePolicy?.platform_audit_events?.max_rows ?? "-"}</Tag>
                      <Tag>container memory: {runtimePolicy?.default_container?.memory ?? "-"}</Tag>
                      <Tag>cpus: {runtimePolicy?.default_container?.cpus ?? "-"}</Tag>
                      <Button size="small" icon={<DeleteOutlined />} loading={loading} onClick={cleanupPlatformAuditEvents}>
                        清理审计事件
                      </Button>
                    </Space>
                    <Table
                      rowKey="id"
                      columns={platformAuditColumns}
                      dataSource={platformAuditEvents}
                      pagination={{ pageSize: 10 }}
                      scroll={{ x: 1200 }}
                    />
                  </Card>
                ),
              },
              {
                key: "reports",
                label: "Reports",
                children: (
                  <Card>
                    <List
                      dataSource={reports}
                      renderItem={(item) => (
                        <List.Item>
                          <List.Item.Meta title={item.kind} description={item.path} />
                          <Space>
                            <Tag>{String(item.summary?.finding_count ?? 0)} findings</Tag>
                            <Button size="small" icon={<FileTextOutlined />} onClick={() => downloadReport(item.report_id)}>下载</Button>
                          </Space>
                        </List.Item>
                      )}
                    />
                  </Card>
                ),
              },
            ]}
          />
          <Drawer
            title={selectedFinding?.finding.title || "Finding"}
            open={Boolean(selectedFinding)}
            width={720}
            onClose={() => setSelectedFinding(undefined)}
          >
            {selectedFinding && (
              <Space direction="vertical" size={16} className="drawer-stack">
                <Space wrap>
                  <Button icon={<SafetyCertificateOutlined />} loading={loading} onClick={runFindingPoc}>运行 PoC 验证</Button>
                </Space>
                <Descriptions bordered size="small" column={1}>
                  <Descriptions.Item label="ID">{selectedFinding.finding.finding_id}</Descriptions.Item>
                  <Descriptions.Item label="Severity"><Tag color={severityColor(selectedFinding.finding.severity)}>{selectedFinding.finding.severity}</Tag></Descriptions.Item>
                  <Descriptions.Item label="Status"><Tag>{selectedFinding.finding.status}</Tag></Descriptions.Item>
                  <Descriptions.Item label="Location">{selectedFinding.finding.file_path || "-"}:{selectedFinding.finding.line_start || "-"}</Descriptions.Item>
                  <Descriptions.Item label="Source">{selectedFinding.finding.source}</Descriptions.Item>
                  <Descriptions.Item label="Description">{selectedFinding.finding.description || "-"}</Descriptions.Item>
                </Descriptions>
                <Collapse
                  items={[
                    {
                      key: "evidence",
                      label: `Evidence (${selectedFinding.evidence.length})`,
                      children: <pre>{JSON.stringify(selectedFinding.evidence, null, 2)}</pre>,
                    },
                    {
                      key: "attempts",
                      label: `Validation Attempts (${selectedFinding.validation_attempts.length})`,
                      children: <pre>{JSON.stringify(selectedFinding.validation_attempts, null, 2)}</pre>,
                    },
                    {
                      key: "raw",
                      label: "Raw",
                      children: <pre>{JSON.stringify(selectedFinding.finding.raw || {}, null, 2)}</pre>,
                    },
                  ]}
                />
              </Space>
            )}
          </Drawer>
          <Drawer
            title="Agent Events"
            open={Boolean(agentEvents)}
            width={720}
            onClose={() => setAgentEvents(undefined)}
          >
            <pre>{JSON.stringify(agentEvents || [], null, 2)}</pre>
          </Drawer>
          <Drawer
            title={`Container Logs - ${containerLogs?.title || ""}`}
            open={Boolean(containerLogs)}
            width={820}
            onClose={() => setContainerLogs(undefined)}
          >
            <pre>{containerLogs?.body || ""}</pre>
          </Drawer>
        </Content>
      </Layout>
    </ConfigProvider>
  );
}

function severityColor(value: string) {
  if (value === "critical" || value === "high") return "red";
  if (value === "medium") return "orange";
  if (value === "low") return "blue";
  return "default";
}

function isActiveRun(auditStatus?: string, pipelineStatus?: string) {
  return ["queued", "running", "validating"].includes(auditStatus || "") || ["queued", "running"].includes(pipelineStatus || "");
}

createRoot(document.getElementById("root")!).render(<App />);

import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  ConfigProvider,
  Form,
  Layout,
  message,
  theme,
} from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { API_KEY_HEADER, API_KEY_STORAGE_KEY, formatHttpError, readJson, rememberApiKeyHeaderName, withAuth } from "./api";
import { AppDrawers } from "./components/AppDrawers";
import { AppHeader } from "./components/AppHeader";
import { AppNavigation } from "./components/AppNavigation";
import { useAppRoute } from "./hooks/useAppRoute";
import { useDashboardColumns } from "./hooks/useDashboardColumns";
import { navigationItems } from "./navigation";
import { AppRoutes } from "./routes/AppRoutes";
import type { AgentRun, ApiKeyRecord, ArtifactRef, AuditRun, AuthStatus, ContainerRow, DependencyInventory, Finding, FindingDetail, KnowledgeDocument, KnowledgeMatch, ManagedRuntime, PipelineStatus, PlatformAuditEvent, Project, ReportArtifact, RuntimePolicy, RuntimeReadiness, SandboxCapabilities, StorageSummary, WorkerHeartbeat } from "./types";
import { artifactFileName, artifactUrl, isActiveRun, parseScopes } from "./utils/format";

const { Content } = Layout;

export function App() {
  const [activeView, setActiveView] = useAppRoute();
  const [apiHealth, setApiHealth] = useState<any>();
  const [authStatus, setAuthStatus] = useState<AuthStatus>();
  const [dockerHealth, setDockerHealth] = useState<any>();
  const [managedRuntime, setManagedRuntime] = useState<ManagedRuntime>();
  const [storageSummary, setStorageSummary] = useState<StorageSummary>();
  const [runtimePolicy, setRuntimePolicy] = useState<RuntimePolicy>();
  const [runtimeReadiness, setRuntimeReadiness] = useState<RuntimeReadiness>();
  const [workerHeartbeats, setWorkerHeartbeats] = useState<WorkerHeartbeat[]>([]);
  const [sandboxCapabilities, setSandboxCapabilities] = useState<SandboxCapabilities>();
  const [apiKeys, setApiKeys] = useState<ApiKeyRecord[]>([]);
  const [platformAuditEvents, setPlatformAuditEvents] = useState<PlatformAuditEvent[]>([]);
  const [knowledgeDocuments, setKnowledgeDocuments] = useState<KnowledgeDocument[]>([]);
  const [knowledgeMatches, setKnowledgeMatches] = useState<KnowledgeMatch[]>([]);
  const [apiKey, setApiKey] = useState(() => window.localStorage.getItem(API_KEY_STORAGE_KEY) || "");
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [auditRun, setAuditRun] = useState<AuditRun>();
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [dependencies, setDependencies] = useState<DependencyInventory>();
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
  const [knowledgeFiles, setKnowledgeFiles] = useState<UploadFile[]>([]);
  const [gitForm] = Form.useForm();
  const [zipForm] = Form.useForm();
  const [apiKeyForm] = Form.useForm();
  const [knowledgeUploadForm] = Form.useForm();
  const [knowledgeSearchForm] = Form.useForm();

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
      rememberApiKeyHeaderName(auth?.api_key_header);
      const [docker, projectRows] = await Promise.all([
        readJson("/gateway/runtime/docker/health"),
        readJson("/gateway/projects"),
      ]);
      setDockerHealth(docker);
      readJson("/gateway/runtime/managed").then(setManagedRuntime).catch(() => setManagedRuntime(undefined));
      readJson("/gateway/runtime/storage").then(setStorageSummary).catch(() => setStorageSummary(undefined));
      readJson("/gateway/runtime/policy").then(setRuntimePolicy).catch(() => setRuntimePolicy(undefined));
      readJson("/gateway/runtime/readiness").then(setRuntimeReadiness).catch(() => setRuntimeReadiness(undefined));
      readJson("/gateway/runtime/workers").then((data) => setWorkerHeartbeats(data.workers || [])).catch(() => setWorkerHeartbeats([]));
      readJson("/gateway/runtime/sandbox/capabilities").then(setSandboxCapabilities).catch(() => setSandboxCapabilities(undefined));
      readJson("/gateway/auth/api-keys").then(setApiKeys).catch(() => setApiKeys([]));
      readJson("/gateway/platform/audit-events?limit=100").then(setPlatformAuditEvents).catch(() => setPlatformAuditEvents([]));
      readJson("/gateway/knowledge/documents").then(setKnowledgeDocuments).catch(() => setKnowledgeDocuments([]));
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
    const [run, agents, findingRows, dependencyRows, containerRows, reportRows, pipeline] = await Promise.all([
      readJson(`/gateway/audit-runs/${auditRunId}`),
      readJson(`/gateway/audit-runs/${auditRunId}/agent-runs`),
      readJson(`/gateway/audit-runs/${auditRunId}/findings`),
      readJson(`/gateway/audit-runs/${auditRunId}/dependencies`).catch(() => undefined),
      readJson(`/gateway/audit-runs/${auditRunId}/containers`),
      readJson(`/gateway/audit-runs/${auditRunId}/reports`),
      readJson(`/gateway/audit-runs/${auditRunId}/pipeline-status`),
    ]);
    setAuditRun(run);
    setAgentRuns(agents);
    setFindings(findingRows);
    setDependencies(dependencyRows);
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
    const zipFile = zipFiles[0]?.originFileObj;
    if (!zipFile) {
      message.error("请选择 zip 文件");
      return;
    }
    await runAction(async () => {
      const formData = new FormData();
      formData.append("name", values.name);
      formData.append("file", zipFile);
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

  async function openArtifact(artifact?: ArtifactRef, fallbackPath?: string) {
    const url = artifactUrl(artifact, fallbackPath);
    if (!url) {
      message.warning("Artifact is not available");
      return;
    }
    await runAction(async () => {
      const response = await fetch(url, withAuth());
      const text = response.ok ? undefined : await response.text();
      if (!response.ok) {
        throw new Error(formatHttpError(text || "", response.statusText));
      }
      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = artifactFileName(artifact, fallbackPath);
      link.rel = "noopener";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
    });
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
        throw new Error(formatHttpError(text, response.statusText));
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

  async function previewLocalStorageCleanup() {
    await runAction(async () => {
      const result = await readJson("/gateway/runtime/storage/cleanup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dry_run: true }),
      });
      setLastResponse(result);
      const summary = await readJson("/gateway/runtime/storage");
      setStorageSummary(summary);
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

  async function createManagedApiKey(values: { name: string; scopes?: string }) {
    await runAction(async () => {
      const result = await readJson("/gateway/auth/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: values.name,
          scopes: parseScopes(values.scopes),
        }),
      });
      setLastResponse(result);
      apiKeyForm.resetFields();
      const rows = await readJson("/gateway/auth/api-keys");
      setApiKeys(rows);
    });
  }

  async function deactivateManagedApiKey(keyId: string) {
    await runAction(async () => {
      const result = await readJson(`/gateway/auth/api-keys/${keyId}/deactivate`, { method: "POST" });
      setLastResponse(result);
      const rows = await readJson("/gateway/auth/api-keys");
      setApiKeys(rows);
    });
  }

  async function uploadKnowledgeDocument(values: { title: string; scope?: string; project_id?: string }) {
    const knowledgeFile = knowledgeFiles[0]?.originFileObj;
    if (!knowledgeFile) {
      message.error("请选择知识库文档");
      return;
    }
    await runAction(async () => {
      const scope = (values.scope || "global").trim().toLowerCase();
      const formData = new FormData();
      formData.append("title", values.title);
      formData.append("scope", scope);
      if (scope === "project" && values.project_id) {
        formData.append("project_id", values.project_id);
      }
      formData.append("file", knowledgeFile);
      const result = await readJson("/gateway/knowledge/documents", { method: "POST", body: formData });
      setLastResponse(result);
      knowledgeUploadForm.resetFields();
      setKnowledgeFiles([]);
      const rows = await readJson("/gateway/knowledge/documents");
      setKnowledgeDocuments(rows);
    });
  }

  async function searchKnowledge(values: { query: string; project_id?: string; limit?: string }) {
    await runAction(async () => {
      const result = await readJson("/gateway/knowledge/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: values.query,
          project_id: values.project_id || selectedProjectId || undefined,
          include_global: true,
          limit: Number(values.limit || 8),
        }),
      });
      setLastResponse(result);
      setKnowledgeMatches(result.matches || []);
    });
  }

  async function reindexKnowledgeDocument(documentId: string) {
    await runAction(async () => {
      const result = await readJson(`/gateway/knowledge/documents/${documentId}/reindex`, { method: "POST" });
      setLastResponse(result);
      const rows = await readJson("/gateway/knowledge/documents");
      setKnowledgeDocuments(rows);
    });
  }

  async function deleteKnowledgeDocument(documentId: string) {
    await runAction(async () => {
      const result = await readJson(`/gateway/knowledge/documents/${documentId}`, { method: "DELETE" });
      setLastResponse(result);
      const rows = await readJson("/gateway/knowledge/documents");
      setKnowledgeDocuments(rows);
      setKnowledgeMatches((items) => items.filter((item) => item.document_id !== documentId));
    });
  }

  function saveApiKey() {
    const normalized = apiKey.trim();
    if (normalized) {
      window.localStorage.setItem(API_KEY_STORAGE_KEY, normalized);
      message.success("API Key saved locally");
    } else {
      window.localStorage.removeItem(API_KEY_STORAGE_KEY);
      message.warning("API Key removed");
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

  const columns = useDashboardColumns({
    onDeactivateManagedApiKey: deactivateManagedApiKey,
    onDeleteKnowledgeDocument: deleteKnowledgeDocument,
    onOpenAgentEvents: openAgentEvents,
    onOpenArtifact: openArtifact,
    onOpenContainerLogs: openContainerLogs,
    onReindexKnowledgeDocument: reindexKnowledgeDocument,
  });

  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm }}>
      <Layout className="app-shell">
        <AppHeader
          activeView={activeView}
          apiKey={apiKey}
          authHeaderName={authStatus?.api_key_header}
          navigationItems={navigationItems}
          onApiKeyChange={setApiKey}
          onRefresh={refresh}
          onSaveApiKey={saveApiKey}
          onViewChange={setActiveView}
        />
        <Layout className="main-layout">
          <AppNavigation activeView={activeView} items={navigationItems} onViewChange={setActiveView} />
          <Content className="app-content">
            {error && <Alert type="error" showIcon message="运行错误" description={error} className="section" />}
            {authStatus?.enabled && !apiKey.trim() && (
              <Alert
                type="warning"
                showIcon
                message="API authentication is enabled"
                description={`Enter a key for ${authStatus.api_key_header || API_KEY_HEADER} before using runtime, project, audit, artifact, and knowledge APIs.`}
                className="section"
              />
            )}
            <AppRoutes
              activeView={activeView}
              agentRuns={agentRuns}
              apiHealth={apiHealth}
              apiKeyForm={apiKeyForm}
              apiKeys={apiKeys}
              auditRun={auditRun}
              authStatus={authStatus}
              columns={columns}
              containers={containers}
              dependencies={dependencies}
              dockerHealth={dockerHealth}
              findings={findings}
              gitForm={gitForm}
              knowledgeDocuments={knowledgeDocuments}
              knowledgeFiles={knowledgeFiles}
              knowledgeMatches={knowledgeMatches}
              knowledgeSearchForm={knowledgeSearchForm}
              knowledgeUploadForm={knowledgeUploadForm}
              lastResponse={lastResponse}
              loading={loading}
              managedRuntime={managedRuntime}
              pipelineStatus={pipelineStatus}
              platformAuditEvents={platformAuditEvents}
              projects={projects}
              reports={reports}
              runtimePolicy={runtimePolicy}
              runtimeReadiness={runtimeReadiness}
              sandboxCapabilities={sandboxCapabilities}
              sandboxTarget={sandboxTarget}
              selectedProject={selectedProject}
              selectedProjectId={selectedProjectId}
              storageSummary={storageSummary}
              workerHeartbeats={workerHeartbeats}
              zipFiles={zipFiles}
              zipForm={zipForm}
              onCancelAuditRun={cancelAuditRun}
              onCleanup={cleanup}
              onCleanupExpiredRuntime={cleanupExpiredRuntime}
              onCleanupPlatformAuditEvents={cleanupPlatformAuditEvents}
              onCreateGitProject={createGitProject}
              onCreateManagedApiKey={createManagedApiKey}
              onGenerateReport={generateReport}
              onOpenArtifact={openArtifact}
              onOpenFinding={openFinding}
              onPreviewLocalStorageCleanup={previewLocalStorageCleanup}
              onRunJudge={runJudge}
              onRunPipeline={runPipeline}
              onRunPocSmoke={runPocSmoke}
              onRunSandboxTargetPoc={runSandboxTargetPoc}
              onRunSca={runSca}
              onSearchKnowledge={searchKnowledge}
              onSelectProject={setSelectedProjectId}
              onSetKnowledgeFiles={setKnowledgeFiles}
              onSetZipFiles={setZipFiles}
              onStartAudit={startAudit}
              onStartSandboxService={startSandboxService}
              onUploadKnowledgeDocument={uploadKnowledgeDocument}
              onUploadZipProject={uploadZipProject}
            />
            <AppDrawers
              agentEvents={agentEvents}
              containerLogs={containerLogs}
              loading={loading}
              selectedFinding={selectedFinding}
              onCloseAgentEvents={() => setAgentEvents(undefined)}
              onCloseContainerLogs={() => setContainerLogs(undefined)}
              onCloseFinding={() => setSelectedFinding(undefined)}
              onOpenArtifact={openArtifact}
              onRunFindingPoc={runFindingPoc}
            />
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

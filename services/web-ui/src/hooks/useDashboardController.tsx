import { useEffect } from "react";
import { message } from "antd";
import { API_KEY_STORAGE_KEY, rememberApiKeyHeaderName } from "../api";
import * as dashboardApi from "../client/dashboardApi";
import type {
  ArtifactRef,
  ContainerRow,
} from "../types";
import { artifactFileName, artifactUrl, isActiveRun, parseCsvList, parseScopes } from "../utils/format";
import { useDashboardColumns } from "./useDashboardColumns";
import { useDashboardState } from "./useDashboardState";

export function useDashboardController() {
  const dashboardState = useDashboardState();
  const {
    agentEvents,
    agentRuns,
    apiHealth,
    apiKey,
    apiKeyForm,
    apiKeys,
    auditRun,
    authStatus,
    clearProtectedState,
    containerLogs,
    containers,
    dependencies,
    dockerHealth,
    error,
    findings,
    gitForm,
    knowledgeDocuments,
    knowledgeFiles,
    knowledgeMatches,
    knowledgeSearchForm,
    knowledgeUploadForm,
    lastResponse,
    loading,
    managedRuntime,
    pipelineStatus,
    platformAuditEvents,
    projects,
    reports,
    runtimePolicy,
    runtimeReadiness,
    sandboxCapabilities,
    sandboxTarget,
    selectedFinding,
    selectedProject,
    selectedProjectId,
    setAgentEvents,
    setAgentRuns,
    setApiHealth,
    setApiKey,
    setApiKeys,
    setAuditRun,
    setAuthStatus,
    setContainerLogs,
    setContainers,
    setDependencies,
    setDockerHealth,
    setError,
    setFindings,
    setKnowledgeDocuments,
    setKnowledgeFiles,
    setKnowledgeMatches,
    setLastResponse,
    setLoading,
    setManagedRuntime,
    setPipelineStatus,
    setPlatformAuditEvents,
    setProjects,
    setReports,
    setRuntimePolicy,
    setRuntimeReadiness,
    setSandboxCapabilities,
    setSandboxTarget,
    setSelectedFinding,
    setSelectedProjectId,
    setStorageSummary,
    setWorkerHeartbeats,
    setZipFiles,
    storageSummary,
    workerHeartbeats,
    zipFiles,
    zipForm,
  } = dashboardState;

  async function refreshAuditRun(auditRunId: string) {
    const bundle = await dashboardApi.getAuditRunBundle(auditRunId);
    setAuditRun(bundle.run);
    setAgentRuns(bundle.agents);
    setFindings(bundle.findings);
    setDependencies(bundle.dependencies);
    setContainers(bundle.containers);
    setReports(bundle.reports);
    setPipelineStatus(bundle.pipeline);
  }

  async function refresh() {
    setError(undefined);
    try {
      const [api, auth] = await dashboardApi.getPlatformBootstrap();
      setApiHealth(api);
      setAuthStatus(auth);
      rememberApiKeyHeaderName(auth?.api_key_header);
      const hasLocalApiKey = Boolean((window.localStorage.getItem(API_KEY_STORAGE_KEY) || "").trim());
      if (auth?.enabled && !hasLocalApiKey) {
        clearProtectedState();
        return;
      }
      const [docker, projectRows] = await dashboardApi.getDashboardProjects();
      setDockerHealth(docker);
      dashboardApi.getManagedRuntime().then(setManagedRuntime).catch(() => setManagedRuntime(undefined));
      dashboardApi.getStorageSummary().then(setStorageSummary).catch(() => setStorageSummary(undefined));
      dashboardApi.getRuntimePolicy().then(setRuntimePolicy).catch(() => setRuntimePolicy(undefined));
      dashboardApi.getRuntimeReadiness().then(setRuntimeReadiness).catch(() => setRuntimeReadiness(undefined));
      dashboardApi.getWorkerHeartbeats().then((data) => setWorkerHeartbeats(data.workers || [])).catch(() => setWorkerHeartbeats([]));
      dashboardApi.getSandboxCapabilities().then(setSandboxCapabilities).catch(() => setSandboxCapabilities(undefined));
      dashboardApi.listApiKeys().then(setApiKeys).catch(() => setApiKeys([]));
      dashboardApi.listPlatformAuditEvents().then(setPlatformAuditEvents).catch(() => setPlatformAuditEvents([]));
      dashboardApi.listKnowledgeDocuments().then(setKnowledgeDocuments).catch(() => setKnowledgeDocuments([]));
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

  async function createGitProject(values: { name: string; git_url: string; ref?: string }) {
    await runAction(async () => {
      const result = await dashboardApi.createGitProject(values);
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
      const result = await dashboardApi.uploadZipProject(formData);
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
      const result = await dashboardApi.createAuditRun(selectedProjectId);
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
      const result = await dashboardApi.runSca(auditRun.audit_run_id);
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
      const result = await dashboardApi.runPipeline(auditRun.audit_run_id);
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
      const result = await dashboardApi.runJudge(auditRun.audit_run_id);
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
      const result = await dashboardApi.generateReport(auditRun.audit_run_id);
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
    });
  }

  function sandboxUnavailableMessage() {
    return (
      sandboxCapabilities?.reason ||
      sandboxCapabilities?.warnings?.[0] ||
      "Sandbox execution is not available. Configure gVisor/Kata or an approved sandbox runtime before running PoC containers."
    );
  }

  function ensureSandboxExecutionAvailable() {
    if (sandboxCapabilities?.sandbox_execution_available) {
      return true;
    }
    message.error(sandboxUnavailableMessage());
    return false;
  }

  async function runPocSmoke() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    await runAction(async () => {
      const result = await dashboardApi.runSandboxPoc(auditRun.audit_run_id, {
        image: "python:3.12-slim",
        command: [
          "python",
          "-c",
          "import os, json; print('dieaudit poc smoke'); print(json.dumps(os.listdir('/workspace')[:20] if os.path.exists('/workspace') else []))",
        ],
        allow_external_network: false,
        timeout_seconds: 120,
        allow_weak_isolation: false,
      });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
      const managed = await dashboardApi.getManagedRuntime();
      setManagedRuntime(managed);
    });
  }

  async function startSandboxService() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    await runAction(async () => {
      const result = await dashboardApi.startSandboxService(auditRun.audit_run_id, {
        image: "python:3.12-slim",
        command: ["python", "-m", "http.server", "8080", "--directory", "/workspace"],
        service_name: "target",
        port: 8080,
        allow_external_network: false,
        retain_runtime_on_failure: true,
        startup_timeout_seconds: 30,
        allow_weak_isolation: false,
      });
      setSandboxTarget({ network: result.network, target_url: result.target_url });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
      const managed = await dashboardApi.getManagedRuntime();
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
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    await runAction(async () => {
      const result = await dashboardApi.runSandboxPoc(auditRun.audit_run_id, {
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
        allow_weak_isolation: false,
      });
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
      const managed = await dashboardApi.getManagedRuntime();
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
      const blob = await dashboardApi.fetchArtifactBlob(url);
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
      const result = await dashboardApi.getFinding(findingId);
      setSelectedFinding(result);
    });
  }

  async function runFindingPoc() {
    if (!selectedFinding || !auditRun) {
      return;
    }
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    const findingId = selectedFinding.finding.finding_id;
    await runAction(async () => {
      const result = await dashboardApi.runFindingPoc(findingId, {
        image: "python:3.12-slim",
        command: [
          "python",
          "-c",
          "import os, json; print('dieaudit finding poc smoke'); print(json.dumps({'workspace': os.listdir('/workspace')[:20] if os.path.exists('/workspace') else [], 'artifact_dir': os.environ.get('ARTIFACT_DIR')}))",
        ],
        allow_external_network: false,
        timeout_seconds: 120,
        expected_exit_code: 0,
        allow_weak_isolation: false,
      });
      setLastResponse(result);
      setSelectedFinding(result.finding);
      await refreshAuditRun(auditRun.audit_run_id);
      const managed = await dashboardApi.getManagedRuntime();
      setManagedRuntime(managed);
    });
  }

  async function openAgentEvents(agentRunId: string) {
    if (!auditRun) {
      return;
    }
    await runAction(async () => {
      const result = await dashboardApi.getAgentEvents(auditRun.audit_run_id, agentRunId);
      setAgentEvents(result);
    });
  }

  async function openContainerLogs(row: ContainerRow) {
    if (!auditRun) {
      return;
    }
    await runAction(async () => {
      const text = await dashboardApi.getContainerLogs(auditRun.audit_run_id, row.Id);
      setContainerLogs({ title: row.container_name || row.Names?.[0]?.replace("/", "") || row.Id.slice(0, 12), body: text });
    });
  }

  async function cleanup() {
    if (!auditRun) {
      return;
    }
    await runAction(async () => {
      const result = await dashboardApi.cleanupAuditRun(auditRun.audit_run_id);
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function cancelAuditRun() {
    if (!auditRun) {
      return;
    }
    await runAction(async () => {
      const result = await dashboardApi.cancelAuditRun(auditRun.audit_run_id);
      setLastResponse(result);
      await refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function cleanupExpiredRuntime() {
    await runAction(async () => {
      const result = await dashboardApi.cleanupExpiredRuntime();
      setLastResponse(result);
      const managed = await dashboardApi.getManagedRuntime();
      setManagedRuntime(managed);
      if (auditRun) {
        await refreshAuditRun(auditRun.audit_run_id);
      }
    });
  }

  async function previewLocalStorageCleanup() {
    await runAction(async () => {
      const result = await dashboardApi.previewLocalStorageCleanup();
      setLastResponse(result);
      const summary = await dashboardApi.getStorageSummary();
      setStorageSummary(summary);
    });
  }

  async function cleanupPlatformAuditEvents() {
    await runAction(async () => {
      const result = await dashboardApi.cleanupPlatformAuditEvents();
      setLastResponse(result);
      const rows = await dashboardApi.listPlatformAuditEvents();
      setPlatformAuditEvents(rows);
    });
  }

  async function createManagedApiKey(values: { name: string; scopes?: string; project_ids?: string; audit_run_ids?: string }) {
    await runAction(async () => {
      const projectIds = parseCsvList(values.project_ids);
      const auditRunIds = parseCsvList(values.audit_run_ids);
      const result = await dashboardApi.createManagedApiKey({
        name: values.name,
        scopes: parseScopes(values.scopes),
        metadata: {
          ...(projectIds.length ? { project_ids: projectIds } : {}),
          ...(auditRunIds.length ? { audit_run_ids: auditRunIds } : {}),
        },
      });
      setLastResponse(result);
      apiKeyForm.resetFields();
      const rows = await dashboardApi.listApiKeys();
      setApiKeys(rows);
    });
  }

  async function deactivateManagedApiKey(keyId: string) {
    await runAction(async () => {
      const result = await dashboardApi.deactivateManagedApiKey(keyId);
      setLastResponse(result);
      const rows = await dashboardApi.listApiKeys();
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
      const result = await dashboardApi.uploadKnowledgeDocument(formData);
      setLastResponse(result);
      knowledgeUploadForm.resetFields();
      setKnowledgeFiles([]);
      const rows = await dashboardApi.listKnowledgeDocuments();
      setKnowledgeDocuments(rows);
    });
  }

  async function searchKnowledge(values: { query: string; project_id?: string; limit?: string }) {
    await runAction(async () => {
      const result = await dashboardApi.searchKnowledge({
        query: values.query,
        project_id: values.project_id || selectedProjectId || undefined,
        include_global: true,
        limit: Number(values.limit || 8),
      });
      setLastResponse(result);
      setKnowledgeMatches(result.matches || []);
    });
  }

  async function reindexKnowledgeDocument(documentId: string) {
    await runAction(async () => {
      const result = await dashboardApi.reindexKnowledgeDocument(documentId);
      setLastResponse(result);
      const rows = await dashboardApi.listKnowledgeDocuments();
      setKnowledgeDocuments(rows);
    });
  }

  async function deleteKnowledgeDocument(documentId: string) {
    await runAction(async () => {
      const result = await dashboardApi.deleteKnowledgeDocument(documentId);
      setLastResponse(result);
      const rows = await dashboardApi.listKnowledgeDocuments();
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

  return {
    actions: {
      cancelAuditRun,
      cleanup,
      cleanupExpiredRuntime,
      cleanupPlatformAuditEvents,
      createGitProject,
      createManagedApiKey,
      generateReport,
      openArtifact,
      openFinding,
      previewLocalStorageCleanup,
      refresh,
      runFindingPoc,
      runJudge,
      runPipeline,
      runPocSmoke,
      runSandboxTargetPoc,
      runSca,
      saveApiKey,
      searchKnowledge,
      setAgentEvents,
      setApiKey,
      setContainerLogs,
      setKnowledgeFiles,
      setSelectedFinding,
      setSelectedProjectId,
      setZipFiles,
      startAudit,
      startSandboxService,
      uploadKnowledgeDocument,
      uploadZipProject,
    },
    columns,
    forms: {
      apiKeyForm,
      gitForm,
      knowledgeSearchForm,
      knowledgeUploadForm,
      zipForm,
    },
    state: {
      agentEvents,
      agentRuns,
      apiHealth,
      apiKey,
      apiKeys,
      auditRun,
      authStatus,
      containerLogs,
      containers,
      dependencies,
      dockerHealth,
      error,
      findings,
      knowledgeDocuments,
      knowledgeFiles,
      knowledgeMatches,
      lastResponse,
      loading,
      managedRuntime,
      pipelineStatus,
      platformAuditEvents,
      projects,
      reports,
      runtimePolicy,
      runtimeReadiness,
      sandboxCapabilities,
      sandboxTarget,
      sandboxExecutionAvailable: Boolean(sandboxCapabilities?.sandbox_execution_available),
      sandboxUnavailableReason: sandboxUnavailableMessage(),
      selectedFinding,
      selectedProject,
      selectedProjectId,
      storageSummary,
      workerHeartbeats,
      zipFiles,
    },
  };
}

export type DashboardController = ReturnType<typeof useDashboardController>;

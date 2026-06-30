import { clearStoredApiKey, getStoredApiKey, rememberApiKeyHeaderName } from "../../api";
import * as dashboardApi from "../../client/dashboardApi";
import type { AppView } from "../../navigation";
import type { DashboardStateController } from "../useDashboardState";

export function useDashboardRefresh(dashboardState: DashboardStateController) {
  const {
    auditRun,
    clearProtectedState,
    selectedProjectId,
    setAgentRuns,
    setApiHealth,
    setApiKeys,
    setAuditRun,
    setApiKey,
    setAuthPrincipal,
    setAuthStatus,
    setCodeAnalysisTasks,
    setContainers,
    setDependencies,
    setExecutionGraph,
    setDockerHealth,
    setError,
    setFindings,
    setKnowledgeDocuments,
    setKnowledgeStatus,
    setLoading,
    setManagedRuntime,
    setPipelineStatus,
    setPlatformAuditEvents,
    setProjects,
    setReports,
    setRuntimePolicy,
    setRuntimeReadiness,
    setSandboxCapabilities,
    setSelectedProjectId,
    setStorageSummary,
    setWhiteboard,
    setWorkerHeartbeats,
  } = dashboardState;

  async function refreshAuditRun(auditRunId: string) {
    const bundle = await dashboardApi.getAuditRunBundle(auditRunId);
    setAuditRun(bundle.run);
    setAgentRuns(bundle.agents);
    setCodeAnalysisTasks(bundle.codeAnalysisTasks);
    setFindings(bundle.findings);
    setDependencies(bundle.dependencies);
    setExecutionGraph(bundle.executionGraph);
    setContainers(bundle.containers);
    setReports(bundle.reports);
    setPipelineStatus(bundle.pipeline);
    setWhiteboard(bundle.whiteboard);
  }

  async function refreshBootstrap() {
    const [api, auth] = await dashboardApi.getPlatformBootstrap();
    setApiHealth(api);
    setAuthStatus(auth);
    rememberApiKeyHeaderName(auth?.api_key_header);
    const hasLocalApiKey = Boolean(getStoredApiKey().trim());
    if (!auth?.enabled) {
      setAuthPrincipal(undefined);
      return true;
    }
    if (!hasLocalApiKey) {
      clearProtectedState();
      return false;
    }
    try {
      const authMe = await dashboardApi.getCurrentAuthPrincipal();
      if (!authMe.authenticated) {
        throw new Error("登录已失效，请重新登录");
      }
      setAuthPrincipal(authMe.principal || undefined);
    } catch (err) {
      clearStoredApiKey();
      setApiKey("");
      clearProtectedState();
      setError(err instanceof Error ? err.message : String(err));
      return false;
    }
    return true;
  }

  async function refreshProjects(preferredProjectId?: string) {
    const projectRows = await dashboardApi.listProjects();
    setProjects(projectRows);
    const nextProjectId = preferredProjectId && projectRows.some((project) => project.project_id === preferredProjectId)
      ? preferredProjectId
      : selectedProjectId && projectRows.some((project) => project.project_id === selectedProjectId)
        ? selectedProjectId
        : projectRows[0]?.project_id;
    if (nextProjectId) {
      setSelectedProjectId(nextProjectId);
    }
    return nextProjectId;
  }

  async function refreshLatestAuditRun(projectId?: string) {
    const nextProjectId = projectId || selectedProjectId;
    if (!nextProjectId) {
      setAuditRun(undefined);
      setAgentRuns([]);
      setCodeAnalysisTasks([]);
      setFindings([]);
      setDependencies(undefined);
      setExecutionGraph(undefined);
      setContainers([]);
      setReports([]);
      setPipelineStatus(undefined);
      setWhiteboard(undefined);
      return;
    }
    if (auditRun?.audit_run_id && auditRun.project_id === nextProjectId) {
      await refreshAuditRun(auditRun.audit_run_id);
      return;
    }
    const runs = await dashboardApi.listProjectAuditRuns(nextProjectId).catch(() => []);
    const latestRun = runs[0];
    if (latestRun?.audit_run_id) {
      await refreshAuditRun(latestRun.audit_run_id);
      return;
    }
    setAuditRun(undefined);
    setAgentRuns([]);
    setCodeAnalysisTasks([]);
    setFindings([]);
    setDependencies(undefined);
    setExecutionGraph(undefined);
    setContainers([]);
    setReports([]);
    setPipelineStatus(undefined);
    setWhiteboard(undefined);
  }

  async function refreshOverview() {
    const [docker, managed, readiness, sandbox] = await Promise.all([
      dashboardApi.getDockerHealth(),
      dashboardApi.getManagedRuntime().catch(() => undefined),
      dashboardApi.getRuntimeReadiness().catch(() => undefined),
      dashboardApi.getSandboxCapabilities().catch(() => undefined),
    ]);
    setDockerHealth(docker);
    setManagedRuntime(managed);
    setRuntimeReadiness(readiness);
    setSandboxCapabilities(sandbox);
    const projectId = await refreshProjects();
    await refreshLatestAuditRun(projectId);
  }

  async function refreshRuntime() {
    const [readiness, workers, sandbox, managed] = await Promise.all([
      dashboardApi.getRuntimeReadiness().catch(() => undefined),
      dashboardApi.getWorkerHeartbeats().catch(() => ({ workers: [] })),
      dashboardApi.getSandboxCapabilities().catch(() => undefined),
      dashboardApi.getManagedRuntime().catch(() => undefined),
    ]);
    setRuntimeReadiness(readiness);
    setWorkerHeartbeats(workers.workers || []);
    setSandboxCapabilities(sandbox);
    setManagedRuntime(managed);
    await refreshLatestAuditRun();
  }

  async function refreshKnowledge() {
    const [rows, status] = await Promise.all([
      dashboardApi.listKnowledgeDocuments(),
      dashboardApi.getKnowledgeStatus().catch(() => undefined),
    ]);
    setKnowledgeDocuments(rows);
    setKnowledgeStatus(status);
    await refreshProjects();
  }

  async function refreshAdmin() {
    const [policy, storage, apiKeyRows, auditEvents] = await Promise.all([
      dashboardApi.getRuntimePolicy().catch(() => undefined),
      dashboardApi.getStorageSummary().catch(() => undefined),
      dashboardApi.listApiKeys().catch(() => []),
      dashboardApi.listPlatformAuditEvents().catch(() => []),
    ]);
    setRuntimePolicy(policy);
    setStorageSummary(storage);
    setApiKeys(apiKeyRows);
    setPlatformAuditEvents(auditEvents);
  }

  async function refreshAuditWorkspace() {
    const projectId = await refreshProjects();
    await refreshLatestAuditRun(projectId);
  }

  async function refreshCurrentView(view: AppView) {
    setError(undefined);
    try {
      const canLoadProtectedData = await refreshBootstrap();
      if (!canLoadProtectedData) {
        return;
      }
      switch (view) {
        case "overview":
          await refreshOverview();
          return;
        case "projects":
          await refreshProjects();
          return;
        case "runtime":
        case "runtime-readiness":
        case "runtime-containers":
        case "runtime-sandbox":
          await refreshRuntime();
          return;
        case "knowledge":
          await refreshKnowledge();
          return;
        case "admin":
          await refreshAdmin();
          return;
        case "audit-runs":
        case "agent-runs":
        case "findings":
        case "finding-review":
        case "dependencies":
        case "reports":
        case "whiteboard":
          await refreshAuditWorkspace();
          return;
        default:
          await refreshOverview();
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

  return {
    refreshAdmin,
    refreshAuditRun,
    refreshCurrentView,
    refreshKnowledge,
    refreshProjects,
    refreshRuntime,
    runAction,
  };
}

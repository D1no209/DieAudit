import { API_KEY_STORAGE_KEY, rememberApiKeyHeaderName } from "../../api";
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
    setAuthStatus,
    setCodeAnalysisTasks,
    setContainers,
    setDependencies,
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
    setWorkerHeartbeats,
  } = dashboardState;

  async function refreshAuditRun(auditRunId: string) {
    const bundle = await dashboardApi.getAuditRunBundle(auditRunId);
    setAuditRun(bundle.run);
    setAgentRuns(bundle.agents);
    setCodeAnalysisTasks(bundle.codeAnalysisTasks);
    setFindings(bundle.findings);
    setDependencies(bundle.dependencies);
    setContainers(bundle.containers);
    setReports(bundle.reports);
    setPipelineStatus(bundle.pipeline);
  }

  async function refreshBootstrap() {
    const [api, auth] = await dashboardApi.getPlatformBootstrap();
    setApiHealth(api);
    setAuthStatus(auth);
    rememberApiKeyHeaderName(auth?.api_key_header);
    const hasLocalApiKey = Boolean((window.localStorage.getItem(API_KEY_STORAGE_KEY) || "").trim());
    if (auth?.enabled && !hasLocalApiKey) {
      clearProtectedState();
      return false;
    }
    return true;
  }

  async function refreshProjects(preferredProjectId?: string) {
    const projectRows = await dashboardApi.listProjects();
    setProjects(projectRows);
    const nextProjectId = preferredProjectId && projectRows.some((project) => project.project_id === preferredProjectId)
      ? preferredProjectId
      : undefined;
    if (nextProjectId) {
      setSelectedProjectId(nextProjectId);
    } else if (!selectedProjectId && projectRows.length > 0) {
      setSelectedProjectId((currentProjectId) => currentProjectId || projectRows[0].project_id);
    }
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
    await refreshProjects();
    if (auditRun) {
      await refreshAuditRun(auditRun.audit_run_id);
    }
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
    if (auditRun) {
      await refreshAuditRun(auditRun.audit_run_id);
    }
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
    await refreshProjects();
    if (auditRun) {
      await refreshAuditRun(auditRun.audit_run_id);
    }
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

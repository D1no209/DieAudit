import { API_KEY_STORAGE_KEY, rememberApiKeyHeaderName } from "../../api";
import * as dashboardApi from "../../client/dashboardApi";
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
    setContainers,
    setDependencies,
    setDockerHealth,
    setError,
    setFindings,
    setKnowledgeDocuments,
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
      dashboardApi
        .getWorkerHeartbeats()
        .then((data) => setWorkerHeartbeats(data.workers || []))
        .catch(() => setWorkerHeartbeats([]));
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

  return { refresh, refreshAuditRun, runAction };
}

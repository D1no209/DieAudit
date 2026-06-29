import { useEffect } from "react";
import type { AppView } from "../navigation";
import { isActiveRun } from "../utils/format";
import { useAdminActions } from "./dashboard/useAdminActions";
import { useAuditRunActions } from "./dashboard/useAuditRunActions";
import { useDashboardRefresh } from "./dashboard/useDashboardRefresh";
import { useKnowledgeActions } from "./dashboard/useKnowledgeActions";
import { useProjectActions } from "./dashboard/useProjectActions";
import { useRuntimeActions } from "./dashboard/useRuntimeActions";
import { useDashboardColumns } from "./useDashboardColumns";
import { useDashboardState } from "./useDashboardState";

export function useDashboardController(activeView: AppView) {
  const dashboardState = useDashboardState();
  const {
    agentEvents,
    agentRuns,
    artifactPreview,
    apiHealth,
    apiKey,
    apiKeys,
    auditRun,
    authStatus,
    codeAnalysisTasks,
    containerLogs,
    containers,
    dependencies,
    executionGraph,
    dockerHealth,
    error,
    findings,
    knowledgeDocuments,
    knowledgeFiles,
    knowledgeMatches,
    knowledgeStatus,
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
    setArtifactPreview,
    setApiKey,
    setContainerLogs,
    setError,
    setKnowledgeFiles,
    setSelectedFinding,
    setSelectedProjectId,
    setZipFiles,
    storageSummary,
    whiteboard,
    workerHeartbeats,
    zipFiles,
  } = dashboardState;

  const runner = useDashboardRefresh(dashboardState);
  const projectActions = useProjectActions(dashboardState, runner);
  const auditRunActions = useAuditRunActions(dashboardState, runner);
  const runtimeActions = useRuntimeActions(dashboardState, runner);
  const knowledgeActions = useKnowledgeActions(dashboardState, runner);
  const adminActions = useAdminActions(dashboardState, runner, activeView);

  useEffect(() => {
    runner.refreshCurrentView(activeView);
  }, [activeView]);

  useEffect(() => {
    if (!auditRun?.audit_run_id || !isActiveRun(auditRun.status, pipelineStatus?.current?.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      runner.refreshAuditRun(auditRun.audit_run_id).catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
      });
    }, 4000);
    return () => window.clearInterval(timer);
  }, [auditRun?.audit_run_id, auditRun?.status, pipelineStatus?.current?.status]);

  const columns = useDashboardColumns({
    onDeactivateManagedApiKey: adminActions.deactivateManagedApiKey,
    onDeleteKnowledgeDocument: knowledgeActions.deleteKnowledgeDocument,
    onOpenAgentEvents: auditRunActions.openAgentEvents,
    onOpenArtifact: auditRunActions.openArtifact,
    onOpenContainerLogs: auditRunActions.openContainerLogs,
    onReindexKnowledgeDocument: knowledgeActions.reindexKnowledgeDocument,
  });

  return {
    actions: {
      ...adminActions,
      ...auditRunActions,
      ...knowledgeActions,
      ...projectActions,
      ...runtimeActions,
      refresh: () => runner.refreshCurrentView(activeView),
      setAgentEvents,
      setArtifactPreview,
      setApiKey,
      setContainerLogs,
      setKnowledgeFiles,
      setSelectedFinding,
      setSelectedProjectId,
      setZipFiles,
    },
    columns,
    forms: {},
    state: {
      agentEvents,
      agentRuns,
      artifactPreview,
      apiHealth,
      apiKey,
      apiKeys,
      auditRun,
      authStatus,
      codeAnalysisTasks,
      containerLogs,
      containers,
      dependencies,
      executionGraph,
      dockerHealth,
      error,
      findings,
      knowledgeDocuments,
      knowledgeFiles,
      knowledgeMatches,
      knowledgeStatus,
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
      sandboxUnavailableReason: runtimeActions.sandboxUnavailableMessage(),
      selectedFinding,
      selectedProject,
      selectedProjectId,
      storageSummary,
      whiteboard,
      workerHeartbeats,
      zipFiles,
    },
  };
}

export type DashboardController = ReturnType<typeof useDashboardController>;

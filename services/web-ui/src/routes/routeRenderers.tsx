import type { ReactNode } from "react";
import type { DashboardController } from "../hooks/useDashboardController";
import { projectHash, type AppView } from "../navigation";
import { AdminPage } from "../pages/AdminPage";
import { AgentMessagesPage } from "../pages/AgentMessagesPage";
import { AgentRunsPage } from "../pages/AgentRunsPage";
import { AuditRunsPage } from "../pages/AuditRunsPage";
import { DependenciesPage } from "../pages/DependenciesPage";
import { FindingReviewPage } from "../pages/FindingReviewPage";
import { FindingsPage } from "../pages/FindingsPage";
import { KnowledgePage } from "../pages/KnowledgePage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { ReportsPage } from "../pages/ReportsPage";
import { SwarmGraphPage } from "../pages/SwarmGraphPage";
import { RuntimePage } from "../pages/RuntimePage";
import { RuntimeContainersPage } from "../pages/RuntimeContainersPage";
import { RuntimeReadinessPage } from "../pages/RuntimeReadinessPage";
import { RuntimeSandboxPage } from "../pages/RuntimeSandboxPage";
import { WhiteboardPage } from "../pages/WhiteboardPage";

export function renderProjectsRoute({ actions, columns, state }: DashboardController) {
  return (
    <ProjectsPage
      loading={state.loading}
      projectColumns={columns.projectColumns}
      projects={state.projects}
      selectedProject={state.selectedProject}
      selectedProjectId={state.selectedProjectId}
      zipFiles={state.zipFiles}
      onCreateGitProject={actions.createGitProject}
      onSelectProject={(projectId) => {
        actions.setSelectedProjectId(projectId);
        window.location.hash = projectHash("project-overview", projectId).replace(/^#/, "");
      }}
      onSetZipFiles={actions.setZipFiles}
      onUploadZipProject={actions.uploadZipProject}
    />
  );
}

export function renderAuditRunsRoute({ actions, state }: DashboardController) {
  return (
    <AuditRunsPage
      agentRunsCount={state.agentRuns.length}
      agentRuntimes={state.agentRuntimes}
      auditRun={state.auditRun}
      codeAnalysisTasks={state.codeAnalysisTasks}
      lastResponse={state.lastResponse}
      loading={state.loading}
      pipelineStatus={state.pipelineStatus}
      reportsCount={state.reports.length}
      selectedProject={state.selectedProject}
      onCancelAuditRun={actions.cancelAuditRun}
      onGenerateReport={actions.generateReport}
      onRunCodeAnalysis={actions.runCodeAnalysis}
      onRunJudge={actions.runJudge}
      onRunPipeline={actions.runPipeline}
      onRunSca={actions.runSca}
      onStartAudit={actions.startAudit}
    />
  );
}

export function renderAgentRunsRoute({ actions, columns, state }: DashboardController, _onViewChange: (view: AppView) => void) {
  return (
    <AgentRunsPage
      agentColumns={columns.agentColumns}
      agentRuns={state.agentRuns}
      auditRun={state.auditRun}
      containers={state.containers}
      executionGraph={state.executionGraph}
      onOpenAgentEvents={actions.openAgentEvents}
      onOpenContainerLogs={actions.openContainerLogs}
      onViewWhiteboard={() => {
        window.location.hash = projectHash("project-whiteboard", state.selectedProjectId, state.auditRun?.audit_run_id).replace(/^#/, "");
      }}
    />
  );
}

export function renderAgentMessagesRoute({ actions, state }: DashboardController) {
  return (
    <AgentMessagesPage
      agentMessages={state.agentMessages}
      agentRuns={state.agentRuns}
      auditRun={state.auditRun}
      loading={state.loading}
      onOpenAgentMessages={actions.openAgentMessages}
    />
  );
}

export function renderFindingsRoute({ actions, state }: DashboardController) {
  return <FindingsPage findings={state.findings} onOpenFinding={actions.openFinding} />;
}

export function renderFindingReviewRoute({ actions, state }: DashboardController, _onViewChange: (view: AppView) => void) {
  return (
    <FindingReviewPage
      loading={state.loading}
      sandboxExecutionAvailable={state.sandboxExecutionAvailable}
      sandboxUnavailableReason={state.sandboxUnavailableReason}
      selectedFinding={state.selectedFinding}
      onOpenArtifact={actions.openArtifact}
      onPreviewArtifact={actions.previewArtifact}
      onRunFindingPoc={actions.runFindingPoc}
      onViewFindings={() => {
        window.location.hash = projectHash("project-findings", state.selectedProjectId, state.auditRun?.audit_run_id).replace(/^#/, "");
      }}
    />
  );
}

export function renderDependenciesRoute({ state }: DashboardController) {
  return <DependenciesPage dependencies={state.dependencies} />;
}

export function renderReportsRoute({ actions, state }: DashboardController) {
  return (
    <ReportsPage
      auditRun={state.auditRun}
      loading={state.loading}
      reports={state.reports}
      onGenerateReport={actions.generateReport}
      onOpenArtifact={actions.openArtifact}
      onPreviewArtifact={actions.previewArtifact}
    />
  );
}

export function renderWhiteboardRoute({ actions, state }: DashboardController) {
  return (
    <WhiteboardPage
      auditRun={state.auditRun}
      loading={state.loading}
      whiteboard={state.whiteboard}
      onRunWhiteboardSwarm={actions.runWhiteboardSwarm}
    />
  );
}

export function renderSwarmRoute({ state }: DashboardController) {
  return <SwarmGraphPage agentRuns={state.agentRuns} auditRun={state.auditRun} whiteboard={state.whiteboard} />;
}

export function renderRuntimeRoute({ actions, columns, state }: DashboardController, onViewChange: (view: AppView) => void) {
  return (
    <RuntimePage
      auditRun={state.auditRun}
      containers={state.containers}
      loading={state.loading}
      runtimeReadiness={state.runtimeReadiness}
      sandboxCapabilities={state.sandboxCapabilities}
      workerHeartbeats={state.workerHeartbeats}
      onCleanup={actions.cleanup}
      onCleanupExpiredRuntime={actions.cleanupExpiredRuntime}
      onViewChange={onViewChange}
    />
  );
}

export function renderRuntimeReadinessRoute({ columns, state }: DashboardController) {
  return (
    <RuntimeReadinessPage
      runtimeReadiness={state.runtimeReadiness}
      workerColumns={columns.workerColumns}
      workerHeartbeats={state.workerHeartbeats}
    />
  );
}

export function renderRuntimeContainersRoute({ columns, state }: DashboardController) {
  return <RuntimeContainersPage containerColumns={columns.containerColumns} containers={state.containers} />;
}

export function renderRuntimeSandboxRoute({ actions, state }: DashboardController) {
  return (
    <RuntimeSandboxPage
      auditRun={state.auditRun}
      loading={state.loading}
      sandboxCapabilities={state.sandboxCapabilities}
      sandboxTarget={state.sandboxTarget}
      sandboxUnavailableReason={state.sandboxUnavailableReason}
      onRunSandboxPoc={actions.runSandboxPoc}
      onRunSandboxTargetPoc={actions.runSandboxTargetPoc}
      onStartSandboxService={actions.startSandboxService}
    />
  );
}

export function renderKnowledgeRoute({ actions, columns, state }: DashboardController) {
  return (
    <KnowledgePage
      knowledgeColumns={columns.knowledgeColumns}
      knowledgeDocuments={state.knowledgeDocuments}
      knowledgeFiles={state.knowledgeFiles}
      knowledgeMatches={state.knowledgeMatches}
      knowledgeStatus={state.knowledgeStatus}
      loading={state.loading}
      selectedProjectId={state.selectedProjectId}
      onSearchKnowledge={actions.searchKnowledge}
      onSetKnowledgeFiles={actions.setKnowledgeFiles}
      onUploadKnowledgeDocument={actions.uploadKnowledgeDocument}
    />
  );
}

export function renderAdminRoute({ actions, columns, state }: DashboardController) {
  return (
    <AdminPage
      agentModelConfig={state.agentModelConfig}
      agentRuntimes={state.agentRuntimes}
      apiKeyColumns={columns.apiKeyColumns}
      apiKeys={state.apiKeys}
      loading={state.loading}
      platformAuditColumns={columns.platformAuditColumns}
      platformAuditEvents={state.platformAuditEvents}
      runtimePolicy={state.runtimePolicy}
      storageSummary={state.storageSummary}
      onCleanupPlatformAuditEvents={actions.cleanupPlatformAuditEvents}
      onCreateManagedApiKey={actions.createManagedApiKey}
      onPreviewLocalStorageCleanup={actions.previewLocalStorageCleanup}
      onUpdateAgentModelConfig={actions.updateAgentModelConfig}
    />
  );
}

export const routeRenderers: Record<AppView, (dashboard: DashboardController, onViewChange: (view: AppView) => void) => ReactNode> = {
  projects: renderProjectsRoute,
  "project-overview": renderProjectsRoute,
  "project-audit-runs": renderAuditRunsRoute,
  "project-agents": renderAgentRunsRoute,
  "project-messages": renderAgentMessagesRoute,
  "project-findings": renderFindingsRoute,
  "project-finding-review": renderFindingReviewRoute,
  "project-dependencies": renderDependenciesRoute,
  "project-whiteboard": renderWhiteboardRoute,
  "project-swarm": renderSwarmRoute,
  "project-reports": renderReportsRoute,
  runtime: renderRuntimeRoute,
  "runtime-readiness": renderRuntimeReadinessRoute,
  "runtime-containers": renderRuntimeContainersRoute,
  "runtime-sandbox": renderRuntimeSandboxRoute,
  knowledge: renderKnowledgeRoute,
  admin: renderAdminRoute,
};

import type { ReactNode } from "react";
import type { DashboardController } from "../hooks/useDashboardController";
import type { AppView } from "../navigation";
import { AdminPage } from "../pages/AdminPage";
import { AgentRunsPage } from "../pages/AgentRunsPage";
import { AuditRunsPage } from "../pages/AuditRunsPage";
import { DependenciesPage } from "../pages/DependenciesPage";
import { FindingReviewPage } from "../pages/FindingReviewPage";
import { FindingsPage } from "../pages/FindingsPage";
import { KnowledgePage } from "../pages/KnowledgePage";
import { OverviewPage } from "../pages/OverviewPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { ReportsPage } from "../pages/ReportsPage";
import { RuntimePage } from "../pages/RuntimePage";
import { RuntimeContainersPage } from "../pages/RuntimeContainersPage";
import { RuntimeReadinessPage } from "../pages/RuntimeReadinessPage";
import { RuntimeSandboxPage } from "../pages/RuntimeSandboxPage";

export function renderOverviewRoute({ state }: DashboardController) {
  return (
    <OverviewPage
      apiHealth={state.apiHealth}
      authStatus={state.authStatus}
      dockerHealth={state.dockerHealth}
      findingsCount={state.findings.length}
      managedRuntime={state.managedRuntime}
      projectsCount={state.projects.length}
      runtimeReadiness={state.runtimeReadiness}
      sandboxCapabilities={state.sandboxCapabilities}
    />
  );
}

export function renderProjectsRoute({ actions, columns, forms, state }: DashboardController) {
  return (
    <ProjectsPage
      gitForm={forms.gitForm}
      loading={state.loading}
      projectColumns={columns.projectColumns}
      projects={state.projects}
      selectedProject={state.selectedProject}
      selectedProjectId={state.selectedProjectId}
      zipFiles={state.zipFiles}
      zipForm={forms.zipForm}
      onCreateGitProject={actions.createGitProject}
      onSelectProject={actions.setSelectedProjectId}
      onSetZipFiles={actions.setZipFiles}
      onUploadZipProject={actions.uploadZipProject}
    />
  );
}

export function renderAuditRunsRoute({ actions, state }: DashboardController) {
  return (
    <AuditRunsPage
      agentRunsCount={state.agentRuns.length}
      auditRun={state.auditRun}
      lastResponse={state.lastResponse}
      loading={state.loading}
      pipelineStatus={state.pipelineStatus}
      reportsCount={state.reports.length}
      selectedProject={state.selectedProject}
      onCancelAuditRun={actions.cancelAuditRun}
      onGenerateReport={actions.generateReport}
      onRunJudge={actions.runJudge}
      onRunPipeline={actions.runPipeline}
      onRunSca={actions.runSca}
      onStartAudit={actions.startAudit}
    />
  );
}

export function renderAgentRunsRoute({ columns, state }: DashboardController) {
  return <AgentRunsPage agentColumns={columns.agentColumns} agentRuns={state.agentRuns} auditRun={state.auditRun} />;
}

export function renderFindingsRoute({ actions, state }: DashboardController) {
  return <FindingsPage findings={state.findings} onOpenFinding={actions.openFinding} />;
}

export function renderFindingReviewRoute({ actions, state }: DashboardController, onViewChange: (view: AppView) => void) {
  return (
    <FindingReviewPage
      loading={state.loading}
      sandboxExecutionAvailable={state.sandboxExecutionAvailable}
      sandboxUnavailableReason={state.sandboxUnavailableReason}
      selectedFinding={state.selectedFinding}
      onOpenArtifact={actions.openArtifact}
      onRunFindingPoc={actions.runFindingPoc}
      onViewFindings={() => onViewChange("findings")}
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
    />
  );
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

export function renderKnowledgeRoute({ actions, columns, forms, state }: DashboardController) {
  return (
    <KnowledgePage
      knowledgeColumns={columns.knowledgeColumns}
      knowledgeDocuments={state.knowledgeDocuments}
      knowledgeFiles={state.knowledgeFiles}
      knowledgeMatches={state.knowledgeMatches}
      knowledgeSearchForm={forms.knowledgeSearchForm}
      knowledgeUploadForm={forms.knowledgeUploadForm}
      loading={state.loading}
      selectedProjectId={state.selectedProjectId}
      onSearchKnowledge={actions.searchKnowledge}
      onSetKnowledgeFiles={actions.setKnowledgeFiles}
      onUploadKnowledgeDocument={actions.uploadKnowledgeDocument}
    />
  );
}

export function renderAdminRoute({ actions, columns, forms, state }: DashboardController) {
  return (
    <AdminPage
      apiKeyColumns={columns.apiKeyColumns}
      apiKeyForm={forms.apiKeyForm}
      apiKeys={state.apiKeys}
      loading={state.loading}
      platformAuditColumns={columns.platformAuditColumns}
      platformAuditEvents={state.platformAuditEvents}
      runtimePolicy={state.runtimePolicy}
      storageSummary={state.storageSummary}
      onCleanupPlatformAuditEvents={actions.cleanupPlatformAuditEvents}
      onCreateManagedApiKey={actions.createManagedApiKey}
      onPreviewLocalStorageCleanup={actions.previewLocalStorageCleanup}
    />
  );
}

export const routeRenderers: Record<AppView, (dashboard: DashboardController, onViewChange: (view: AppView) => void) => ReactNode> = {
  overview: renderOverviewRoute,
  projects: renderProjectsRoute,
  "audit-runs": renderAuditRunsRoute,
  "agent-runs": renderAgentRunsRoute,
  findings: renderFindingsRoute,
  "finding-review": renderFindingReviewRoute,
  dependencies: renderDependenciesRoute,
  reports: renderReportsRoute,
  runtime: renderRuntimeRoute,
  "runtime-readiness": renderRuntimeReadinessRoute,
  "runtime-containers": renderRuntimeContainersRoute,
  "runtime-sandbox": renderRuntimeSandboxRoute,
  knowledge: renderKnowledgeRoute,
  admin: renderAdminRoute,
};

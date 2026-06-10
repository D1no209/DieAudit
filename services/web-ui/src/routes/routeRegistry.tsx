import type { ReactNode } from "react";
import type { DashboardController } from "../hooks/useDashboardController";
import type { AppView } from "../navigation";
import { AdminPage } from "../pages/AdminPage";
import { AgentRunsPage } from "../pages/AgentRunsPage";
import { AuditRunsPage } from "../pages/AuditRunsPage";
import { DependenciesPage } from "../pages/DependenciesPage";
import { FindingsPage } from "../pages/FindingsPage";
import { KnowledgePage } from "../pages/KnowledgePage";
import { OverviewPage } from "../pages/OverviewPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { ReportsPage } from "../pages/ReportsPage";
import { RuntimePage } from "../pages/RuntimePage";

type RouteDefinition = {
  render: (dashboard: DashboardController) => ReactNode;
};

export const routeRegistry: Record<AppView, RouteDefinition> = {
  overview: {
    render: ({ state }) => (
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
    ),
  },
  projects: {
    render: ({ actions, columns, forms, state }) => (
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
    ),
  },
  "audit-runs": {
    render: ({ actions, state }) => (
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
    ),
  },
  "agent-runs": {
    render: ({ columns, state }) => (
      <AgentRunsPage agentColumns={columns.agentColumns} agentRuns={state.agentRuns} auditRun={state.auditRun} />
    ),
  },
  findings: {
    render: ({ actions, state }) => <FindingsPage findings={state.findings} onOpenFinding={actions.openFinding} />,
  },
  dependencies: {
    render: ({ state }) => <DependenciesPage dependencies={state.dependencies} />,
  },
  reports: {
    render: ({ actions, state }) => (
      <ReportsPage
        auditRun={state.auditRun}
        loading={state.loading}
        reports={state.reports}
        onGenerateReport={actions.generateReport}
        onOpenArtifact={actions.openArtifact}
      />
    ),
  },
  runtime: {
    render: ({ actions, columns, state }) => (
      <RuntimePage
        containerColumns={columns.containerColumns}
        containers={state.containers}
        loading={state.loading}
        runtimeReadiness={state.runtimeReadiness}
        sandboxCapabilities={state.sandboxCapabilities}
        sandboxTarget={state.sandboxTarget}
        workerColumns={columns.workerColumns}
        workerHeartbeats={state.workerHeartbeats}
        onCleanup={actions.cleanup}
        onCleanupExpiredRuntime={actions.cleanupExpiredRuntime}
        onRunPocSmoke={actions.runPocSmoke}
        onRunSandboxTargetPoc={actions.runSandboxTargetPoc}
        onStartSandboxService={actions.startSandboxService}
      />
    ),
  },
  knowledge: {
    render: ({ actions, columns, forms, state }) => (
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
    ),
  },
  admin: {
    render: ({ actions, columns, forms, state }) => (
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
    ),
  },
};

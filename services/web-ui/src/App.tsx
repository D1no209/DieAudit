import { Alert, ConfigProvider, Layout, theme } from "antd";
import { API_KEY_HEADER } from "./api";
import { AppDrawers } from "./components/AppDrawers";
import { AppHeader } from "./components/AppHeader";
import { AppNavigation } from "./components/AppNavigation";
import { useAppRoute } from "./hooks/useAppRoute";
import { useDashboardController } from "./hooks/useDashboardController";
import { navigationItems } from "./navigation";
import { AppRoutes } from "./routes/AppRoutes";

const { Content } = Layout;

export function App() {
  const [activeView, setActiveView] = useAppRoute();
  const { actions, columns, forms, state } = useDashboardController();

  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm }}>
      <Layout className="app-shell">
        <AppHeader
          activeView={activeView}
          apiKey={state.apiKey}
          authHeaderName={state.authStatus?.api_key_header}
          navigationItems={navigationItems}
          onApiKeyChange={actions.setApiKey}
          onRefresh={actions.refresh}
          onSaveApiKey={actions.saveApiKey}
          onViewChange={setActiveView}
        />
        <Layout className="main-layout">
          <AppNavigation activeView={activeView} items={navigationItems} onViewChange={setActiveView} />
          <Content className="app-content">
            {state.error && <Alert type="error" showIcon message="运行错误" description={state.error} className="section" />}
            {state.authStatus?.enabled && !state.apiKey.trim() && (
              <Alert
                type="warning"
                showIcon
                message="API authentication is enabled"
                description={`Enter a key for ${state.authStatus.api_key_header || API_KEY_HEADER} before using runtime, project, audit, artifact, and knowledge APIs.`}
                className="section"
              />
            )}
            <AppRoutes
              activeView={activeView}
              agentRuns={state.agentRuns}
              apiHealth={state.apiHealth}
              apiKeyForm={forms.apiKeyForm}
              apiKeys={state.apiKeys}
              auditRun={state.auditRun}
              authStatus={state.authStatus}
              columns={columns}
              containers={state.containers}
              dependencies={state.dependencies}
              dockerHealth={state.dockerHealth}
              findings={state.findings}
              gitForm={forms.gitForm}
              knowledgeDocuments={state.knowledgeDocuments}
              knowledgeFiles={state.knowledgeFiles}
              knowledgeMatches={state.knowledgeMatches}
              knowledgeSearchForm={forms.knowledgeSearchForm}
              knowledgeUploadForm={forms.knowledgeUploadForm}
              lastResponse={state.lastResponse}
              loading={state.loading}
              managedRuntime={state.managedRuntime}
              pipelineStatus={state.pipelineStatus}
              platformAuditEvents={state.platformAuditEvents}
              projects={state.projects}
              reports={state.reports}
              runtimePolicy={state.runtimePolicy}
              runtimeReadiness={state.runtimeReadiness}
              sandboxCapabilities={state.sandboxCapabilities}
              sandboxTarget={state.sandboxTarget}
              selectedProject={state.selectedProject}
              selectedProjectId={state.selectedProjectId}
              storageSummary={state.storageSummary}
              workerHeartbeats={state.workerHeartbeats}
              zipFiles={state.zipFiles}
              zipForm={forms.zipForm}
              onCancelAuditRun={actions.cancelAuditRun}
              onCleanup={actions.cleanup}
              onCleanupExpiredRuntime={actions.cleanupExpiredRuntime}
              onCleanupPlatformAuditEvents={actions.cleanupPlatformAuditEvents}
              onCreateGitProject={actions.createGitProject}
              onCreateManagedApiKey={actions.createManagedApiKey}
              onGenerateReport={actions.generateReport}
              onOpenArtifact={actions.openArtifact}
              onOpenFinding={actions.openFinding}
              onPreviewLocalStorageCleanup={actions.previewLocalStorageCleanup}
              onRunJudge={actions.runJudge}
              onRunPipeline={actions.runPipeline}
              onRunPocSmoke={actions.runPocSmoke}
              onRunSandboxTargetPoc={actions.runSandboxTargetPoc}
              onRunSca={actions.runSca}
              onSearchKnowledge={actions.searchKnowledge}
              onSelectProject={actions.setSelectedProjectId}
              onSetKnowledgeFiles={actions.setKnowledgeFiles}
              onSetZipFiles={actions.setZipFiles}
              onStartAudit={actions.startAudit}
              onStartSandboxService={actions.startSandboxService}
              onUploadKnowledgeDocument={actions.uploadKnowledgeDocument}
              onUploadZipProject={actions.uploadZipProject}
            />
            <AppDrawers
              agentEvents={state.agentEvents}
              containerLogs={state.containerLogs}
              loading={state.loading}
              sandboxExecutionAvailable={state.sandboxExecutionAvailable}
              sandboxUnavailableReason={state.sandboxUnavailableReason}
              selectedFinding={state.selectedFinding}
              onCloseAgentEvents={() => actions.setAgentEvents(undefined)}
              onCloseContainerLogs={() => actions.setContainerLogs(undefined)}
              onCloseFinding={() => actions.setSelectedFinding(undefined)}
              onOpenArtifact={actions.openArtifact}
              onRunFindingPoc={actions.runFindingPoc}
            />
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

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
  const dashboard = useDashboardController();
  const { actions, state } = dashboard;

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
            <AppRoutes activeView={activeView} dashboard={dashboard} />
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

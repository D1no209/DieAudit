import { ConfigProvider, theme } from "antd";
import { AppDrawers } from "./components/AppDrawers";
import { AppShell } from "./components/AppShell";
import { AppStatusAlerts } from "./components/AppStatusAlerts";
import { useAppRoute } from "./hooks/useAppRoute";
import { useDashboardController } from "./hooks/useDashboardController";
import { navigationGroups, navigationItems } from "./navigation";
import { AppRoutes } from "./routes/AppRoutes";

export function App() {
  const [activeView, setActiveView] = useAppRoute();
  const dashboard = useDashboardController();
  const { actions, state } = dashboard;

  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm }}>
      <AppShell
        activeView={activeView}
        alerts={<AppStatusAlerts apiKey={state.apiKey} authStatus={state.authStatus} error={state.error} />}
        apiKey={state.apiKey}
        authHeaderName={state.authStatus?.api_key_header}
        navigationGroups={navigationGroups}
        navigationItems={navigationItems}
        onApiKeyChange={actions.setApiKey}
        onRefresh={actions.refresh}
        onSaveApiKey={actions.saveApiKey}
        onViewChange={setActiveView}
      >
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
      </AppShell>
    </ConfigProvider>
  );
}

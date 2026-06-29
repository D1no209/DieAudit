import { MotionConfig } from "motion/react";
import { AuditContextBar } from "./components/AuditContextBar";
import { AppDrawers } from "./components/AppDrawers";
import { AppShell } from "./components/AppShell";
import { AppStatusAlerts } from "./components/AppStatusAlerts";
import { useAppRoute } from "./hooks/useAppRoute";
import { useDashboardController } from "./hooks/useDashboardController";
import { navigationGroups, navigationItems } from "./navigation";
import { AppRoutes } from "./routes/AppRoutes";
import { ToastHost } from "./ui/ToastHost";

export function App() {
  const [activeView, setActiveView] = useAppRoute();
  const dashboard = useDashboardController(activeView);
  const { actions, state } = dashboard;

  return (
    <MotionConfig reducedMotion="user">
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
        <AuditContextBar
          activeView={activeView}
          agentRunsCount={state.agentRuns.length}
          auditRun={state.auditRun}
          findingsCount={state.findings.length}
          reportsCount={state.reports.length}
          selectedProject={state.selectedProject}
          onViewChange={setActiveView}
        />
        <AppRoutes activeView={activeView} dashboard={dashboard} onViewChange={setActiveView} />
        <AppDrawers
          agentEvents={state.agentEvents}
          artifactPreview={state.artifactPreview}
          containerLogs={state.containerLogs}
          onCloseAgentEvents={() => actions.setAgentEvents(undefined)}
          onCloseArtifactPreview={() => actions.setArtifactPreview(undefined)}
          onCloseContainerLogs={() => actions.setContainerLogs(undefined)}
        />
      </AppShell>
      <ToastHost />
    </MotionConfig>
  );
}

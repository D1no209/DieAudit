import { MotionConfig } from "motion/react";
import { AuditContextBar } from "./components/AuditContextBar";
import { AppDrawers } from "./components/AppDrawers";
import { AppShell } from "./components/AppShell";
import { AppStatusAlerts } from "./components/AppStatusAlerts";
import { useAppRoute } from "./hooks/useAppRoute";
import { useDashboardController } from "./hooks/useDashboardController";
import { navigationGroups, navigationItems } from "./navigation";
import { LoginPage } from "./pages/LoginPage";
import { AppRoutes } from "./routes/AppRoutes";
import { ToastHost } from "./ui/ToastHost";

export function App() {
  const [activeView, setActiveView] = useAppRoute();
  const dashboard = useDashboardController(activeView);
  const { actions, state } = dashboard;
  const loginRequired = Boolean(state.authStatus?.enabled && !state.apiKey.trim());

  if (loginRequired) {
    return (
      <MotionConfig reducedMotion="user">
        <LoginPage
          error={state.error}
          loading={state.loading}
          onLogin={actions.login}
        />
        <ToastHost />
      </MotionConfig>
    );
  }

  return (
    <MotionConfig reducedMotion="user">
      <AppShell
        activeView={activeView}
        alerts={<AppStatusAlerts error={state.error} />}
        authEnabled={state.authStatus?.enabled}
        authPrincipal={state.authPrincipal}
        apiHealth={state.apiHealth}
        dockerHealth={state.dockerHealth}
        navigationGroups={navigationGroups}
        navigationItems={navigationItems}
        runtimeReadiness={state.runtimeReadiness}
        selectedAuditRun={state.auditRun}
        selectedProject={state.selectedProject}
        onLogout={actions.logout}
        onRefresh={actions.refresh}
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

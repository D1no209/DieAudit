import type { ReactNode } from "react";
import type { AppView, NavigationGroup, NavigationItem } from "../navigation";
import type { ApiHealth, AuditRun, AuthPrincipal, DockerHealth, Project, RuntimeReadiness } from "../types";
import { AppHeader } from "./AppHeader";
import { AppNavigation } from "./AppNavigation";

type Props = {
  activeView: AppView;
  alerts?: ReactNode;
  apiHealth?: ApiHealth;
  authEnabled?: boolean;
  authPrincipal?: AuthPrincipal;
  children: ReactNode;
  dockerHealth?: DockerHealth;
  navigationGroups: NavigationGroup[];
  navigationItems: NavigationItem[];
  runtimeReadiness?: RuntimeReadiness;
  selectedAuditRun?: AuditRun;
  selectedProject?: Project;
  onLogout: () => void;
  onRefresh: () => void;
  onViewChange: (view: AppView) => void;
};

export function AppShell({
  activeView,
  alerts,
  apiHealth,
  authEnabled,
  authPrincipal,
  children,
  dockerHealth,
  navigationGroups,
  navigationItems,
  runtimeReadiness,
  selectedAuditRun,
  selectedProject,
  onLogout,
  onRefresh,
  onViewChange,
}: Props) {
  return (
    <div className="min-h-dvh bg-slate-100">
      <AppHeader
        activeView={activeView}
        apiHealth={apiHealth}
        authEnabled={authEnabled}
        authPrincipal={authPrincipal}
        dockerHealth={dockerHealth}
        navigationItems={navigationItems}
        runtimeReadiness={runtimeReadiness}
        selectedAuditRun={selectedAuditRun}
        selectedProject={selectedProject}
        onLogout={onLogout}
        onRefresh={onRefresh}
        onViewChange={onViewChange}
      />
      <div className="flex min-h-[calc(100dvh-64px)]">
        <AppNavigation activeView={activeView} groups={navigationGroups} onViewChange={onViewChange} />
        <main className="mx-auto w-full max-w-[1500px] px-3 py-4 sm:px-4 lg:px-6">
          {alerts}
          {children}
        </main>
      </div>
    </div>
  );
}

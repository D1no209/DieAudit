import type { ReactNode } from "react";
import type { AppView, NavigationGroup, NavigationItem } from "../navigation";
import type { AuthPrincipal } from "../types";
import { AppHeader } from "./AppHeader";
import { AppNavigation } from "./AppNavigation";

type Props = {
  activeView: AppView;
  alerts?: ReactNode;
  authEnabled?: boolean;
  authPrincipal?: AuthPrincipal;
  children: ReactNode;
  navigationGroups: NavigationGroup[];
  navigationItems: NavigationItem[];
  onLogout: () => void;
  onRefresh: () => void;
  onViewChange: (view: AppView) => void;
};

export function AppShell({
  activeView,
  alerts,
  authEnabled,
  authPrincipal,
  children,
  navigationGroups,
  navigationItems,
  onLogout,
  onRefresh,
  onViewChange,
}: Props) {
  return (
    <div className="min-h-dvh bg-slate-100">
      <AppHeader
        activeView={activeView}
        authEnabled={authEnabled}
        authPrincipal={authPrincipal}
        navigationItems={navigationItems}
        onLogout={onLogout}
        onRefresh={onRefresh}
        onViewChange={onViewChange}
      />
      <div className="flex min-h-[calc(100dvh-76px)]">
        <AppNavigation activeView={activeView} groups={navigationGroups} onViewChange={onViewChange} />
        <main className="mx-auto w-full max-w-[1440px] px-4 py-5 sm:px-6 lg:px-8">
          {alerts}
          {children}
        </main>
      </div>
    </div>
  );
}

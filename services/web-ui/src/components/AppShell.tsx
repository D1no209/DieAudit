import type { ReactNode } from "react";
import type { AppView, NavigationGroup, NavigationItem } from "../navigation";
import { AppHeader } from "./AppHeader";
import { AppNavigation } from "./AppNavigation";

type Props = {
  activeView: AppView;
  alerts?: ReactNode;
  apiKey: string;
  authHeaderName?: string;
  children: ReactNode;
  navigationGroups: NavigationGroup[];
  navigationItems: NavigationItem[];
  onApiKeyChange: (value: string) => void;
  onRefresh: () => void;
  onSaveApiKey: () => void;
  onViewChange: (view: AppView) => void;
};

export function AppShell({
  activeView,
  alerts,
  apiKey,
  authHeaderName,
  children,
  navigationGroups,
  navigationItems,
  onApiKeyChange,
  onRefresh,
  onSaveApiKey,
  onViewChange,
}: Props) {
  return (
    <div className="min-h-dvh bg-slate-100">
      <AppHeader
        activeView={activeView}
        apiKey={apiKey}
        authHeaderName={authHeaderName}
        navigationItems={navigationItems}
        onApiKeyChange={onApiKeyChange}
        onRefresh={onRefresh}
        onSaveApiKey={onSaveApiKey}
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

import { Layout } from "antd";
import type { ReactNode } from "react";
import type { AppView, NavigationGroup, NavigationItem } from "../navigation";
import { AppHeader } from "./AppHeader";
import { AppNavigation } from "./AppNavigation";

const { Content } = Layout;

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
    <Layout className="app-shell">
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
      <Layout className="main-layout">
        <AppNavigation activeView={activeView} groups={navigationGroups} onViewChange={onViewChange} />
        <Content className="app-content">
          {alerts}
          {children}
        </Content>
      </Layout>
    </Layout>
  );
}

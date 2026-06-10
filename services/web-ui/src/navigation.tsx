import {
  ApiOutlined,
  BugOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  RobotOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import type { ReactNode } from "react";

export type AppView =
  | "overview"
  | "projects"
  | "audit-runs"
  | "agent-runs"
  | "findings"
  | "dependencies"
  | "reports"
  | "runtime"
  | "knowledge"
  | "admin";

export const DEFAULT_VIEW: AppView = "overview";

export const APP_VIEW_PATHS: Record<AppView, string> = {
  overview: "/overview",
  projects: "/projects",
  "audit-runs": "/audit-runs",
  "agent-runs": "/agent-runs",
  findings: "/findings",
  dependencies: "/dependencies",
  reports: "/reports",
  runtime: "/runtime",
  knowledge: "/knowledge",
  admin: "/admin",
};

const APP_VIEWS = new Set<AppView>(Object.keys(APP_VIEW_PATHS) as AppView[]);

export function appViewFromHash(hash: string): AppView {
  const normalized = hash.replace(/^#/, "").trim() || APP_VIEW_PATHS[DEFAULT_VIEW];
  const directMatch = (Object.entries(APP_VIEW_PATHS) as Array<[AppView, string]>).find(([, path]) => path === normalized);
  if (directMatch) {
    return directMatch[0];
  }

  const fallback = normalized.replace(/^\//, "") as AppView;
  return APP_VIEWS.has(fallback) ? fallback : DEFAULT_VIEW;
}

export function hashFromAppView(view: AppView): string {
  return `#${APP_VIEW_PATHS[view] || APP_VIEW_PATHS[DEFAULT_VIEW]}`;
}

export type NavigationItem = {
  key: AppView;
  icon: ReactNode;
  label: string;
};

export type NavigationGroup = {
  key: string;
  label: string;
  items: NavigationItem[];
};

export const navigationGroups: NavigationGroup[] = [
  {
    key: "workspace",
    label: "Workspace",
    items: [
      { key: "overview", icon: <ApiOutlined />, label: "Overview" },
      { key: "projects", icon: <FolderOpenOutlined />, label: "Projects" },
    ],
  },
  {
    key: "audit",
    label: "Audit Workflow",
    items: [
      { key: "audit-runs", icon: <PlayCircleOutlined />, label: "Audit Runs" },
      { key: "agent-runs", icon: <RobotOutlined />, label: "Agent Runs" },
      { key: "findings", icon: <BugOutlined />, label: "Findings" },
      { key: "dependencies", icon: <DatabaseOutlined />, label: "Dependencies" },
      { key: "reports", icon: <FileTextOutlined />, label: "Reports" },
    ],
  },
  {
    key: "operations",
    label: "Operations",
    items: [
      { key: "runtime", icon: <CloudServerOutlined />, label: "Runtime" },
      { key: "knowledge", icon: <FileTextOutlined />, label: "Knowledge" },
      { key: "admin", icon: <SafetyCertificateOutlined />, label: "Admin" },
    ],
  },
];

export const navigationItems: NavigationItem[] = navigationGroups.flatMap((group) => group.items);

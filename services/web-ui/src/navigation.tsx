import {
  Activity,
  Bot,
  Boxes,
  Bug,
  Database,
  FileText,
  FolderOpen,
  GitBranch,
  Network,
  PlayCircle,
  ShieldCheck,
} from "lucide-react";
import type { ReactNode } from "react";

export type AppView =
  | "overview"
  | "projects"
  | "audit-runs"
  | "agent-runs"
  | "findings"
  | "finding-review"
  | "dependencies"
  | "whiteboard"
  | "reports"
  | "runtime"
  | "runtime-readiness"
  | "runtime-containers"
  | "runtime-sandbox"
  | "knowledge"
  | "admin";

export const DEFAULT_VIEW: AppView = "overview";

export const APP_VIEW_PATHS: Record<AppView, string> = {
  overview: "/overview",
  projects: "/projects",
  "audit-runs": "/audit-runs",
  "agent-runs": "/agent-runs",
  findings: "/findings",
  "finding-review": "/findings/review",
  dependencies: "/dependencies",
  whiteboard: "/whiteboard",
  reports: "/reports",
  runtime: "/runtime",
  "runtime-readiness": "/runtime/readiness",
  "runtime-containers": "/runtime/containers",
  "runtime-sandbox": "/runtime/sandbox",
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
      { key: "overview", icon: <Activity className="h-4 w-4" />, label: "Overview" },
      { key: "projects", icon: <FolderOpen className="h-4 w-4" />, label: "Projects" },
    ],
  },
  {
    key: "audit",
    label: "Audit Workflow",
    items: [
      { key: "audit-runs", icon: <PlayCircle className="h-4 w-4" />, label: "Audit Runs" },
      { key: "agent-runs", icon: <Bot className="h-4 w-4" />, label: "Agent Runs" },
      { key: "findings", icon: <Bug className="h-4 w-4" />, label: "Findings" },
      { key: "finding-review", icon: <ShieldCheck className="h-4 w-4" />, label: "Finding Review" },
      { key: "dependencies", icon: <Database className="h-4 w-4" />, label: "Dependencies" },
      { key: "whiteboard", icon: <GitBranch className="h-4 w-4" />, label: "Whiteboard" },
      { key: "reports", icon: <FileText className="h-4 w-4" />, label: "Reports" },
    ],
  },
  {
    key: "operations",
    label: "Operations",
    items: [
      { key: "runtime", icon: <Network className="h-4 w-4" />, label: "Runtime" },
      { key: "runtime-readiness", icon: <ShieldCheck className="h-4 w-4" />, label: "Readiness" },
      { key: "runtime-containers", icon: <Boxes className="h-4 w-4" />, label: "Containers" },
      { key: "runtime-sandbox", icon: <PlayCircle className="h-4 w-4" />, label: "Sandbox" },
      { key: "knowledge", icon: <FileText className="h-4 w-4" />, label: "Knowledge" },
      { key: "admin", icon: <ShieldCheck className="h-4 w-4" />, label: "Admin" },
    ],
  },
];

export const navigationItems: NavigationItem[] = navigationGroups.flatMap((group) => group.items);

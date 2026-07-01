import {
  Boxes,
  Bot,
  Bug,
  FileText,
  FolderOpen,
  GitBranch,
  Network,
  PlayCircle,
  ShieldCheck,
} from "lucide-react";
import type { ReactNode } from "react";

export type AppView =
  | "projects"
  | "project-overview"
  | "project-audit-runs"
  | "project-agents"
  | "project-messages"
  | "project-findings"
  | "project-finding-review"
  | "project-dependencies"
  | "project-whiteboard"
  | "project-swarm"
  | "project-reports"
  | "runtime"
  | "runtime-readiness"
  | "runtime-containers"
  | "runtime-sandbox"
  | "knowledge"
  | "admin";

export type ProjectRouteState = {
  projectId?: string;
  auditRunId?: string;
  tab: AppView;
};

export const DEFAULT_VIEW: AppView = "projects";

export const APP_VIEW_PATHS: Record<AppView, string> = {
  projects: "/projects",
  "project-overview": "/projects",
  "project-audit-runs": "/projects",
  "project-agents": "/projects",
  "project-messages": "/projects",
  "project-findings": "/projects",
  "project-finding-review": "/projects",
  "project-dependencies": "/projects",
  "project-whiteboard": "/projects",
  "project-swarm": "/projects",
  "project-reports": "/projects",
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
  const projectRoute = projectRouteFromHash(hash);
  if (projectRoute.projectId) {
    return projectRoute.tab;
  }
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

export function projectRouteFromHash(hash: string): ProjectRouteState {
  const normalized = hash.replace(/^#/, "").trim();
  const parts = normalized.split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] !== "projects" || !parts[1]) {
    return { tab: DEFAULT_VIEW };
  }
  const projectId = parts[1];
  const auditRunIndex = parts.indexOf("audit-runs");
  const auditRunId = auditRunIndex >= 0 ? parts[auditRunIndex + 1] : undefined;
  const leaf = parts[parts.length - 1];
  if (leaf === "agents") return { projectId, auditRunId, tab: "project-agents" };
  if (leaf === "messages") return { projectId, auditRunId, tab: "project-messages" };
  if (leaf === "findings") return { projectId, auditRunId, tab: "project-findings" };
  if (leaf === "review") return { projectId, auditRunId, tab: "project-finding-review" };
  if (leaf === "dependencies") return { projectId, auditRunId, tab: "project-dependencies" };
  if (leaf === "reports") return { projectId, auditRunId, tab: "project-reports" };
  if (leaf === "whiteboard") return { projectId, auditRunId, tab: "project-whiteboard" };
  if (leaf === "swarm") return { projectId, auditRunId, tab: "project-swarm" };
  if (parts[2] === "audit-runs") return { projectId, auditRunId, tab: "project-audit-runs" };
  return { projectId, auditRunId, tab: "project-overview" };
}

export function projectHash(view: AppView, projectId?: string, auditRunId?: string): string {
  if (!projectId) return hashFromAppView("projects");
  const projectBase = `#/projects/${encodeURIComponent(projectId)}`;
  const runBase = auditRunId ? `${projectBase}/audit-runs/${encodeURIComponent(auditRunId)}` : `${projectBase}/audit-runs`;
  switch (view) {
    case "project-overview":
      return projectBase;
    case "project-audit-runs":
      return `${projectBase}/audit-runs`;
    case "project-agents":
      return `${runBase}/agents`;
    case "project-messages":
      return `${runBase}/messages`;
    case "project-findings":
      return `${runBase}/findings`;
    case "project-finding-review":
      return `${runBase}/findings/review`;
    case "project-dependencies":
      return `${runBase}/dependencies`;
    case "project-reports":
      return `${runBase}/reports`;
    case "project-whiteboard":
      return `${runBase}/whiteboard`;
    case "project-swarm":
      return `${runBase}/swarm`;
    default:
      return hashFromAppView(view);
  }
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
    label: "Prepare",
    items: [
      { key: "projects", icon: <FolderOpen className="h-4 w-4" />, label: "Projects" },
      { key: "knowledge", icon: <FileText className="h-4 w-4" />, label: "Knowledge" },
    ],
  },
  {
    key: "run",
    label: "Run",
    items: [
      { key: "project-audit-runs", icon: <PlayCircle className="h-4 w-4" />, label: "Audit Runs" },
      { key: "project-overview", icon: <ShieldCheck className="h-4 w-4" />, label: "Pipeline" },
    ],
  },
  {
    key: "inspect",
    label: "Inspect",
    items: [
      { key: "project-agents", icon: <Bot className="h-4 w-4" />, label: "Agent Runs" },
      { key: "runtime-containers", icon: <Boxes className="h-4 w-4" />, label: "Containers" },
      { key: "project-whiteboard", icon: <GitBranch className="h-4 w-4" />, label: "Whiteboard" },
      { key: "project-swarm", icon: <Network className="h-4 w-4" />, label: "Flow Graph" },
    ],
  },
  {
    key: "validate",
    label: "Validate",
    items: [
      { key: "project-findings", icon: <Bug className="h-4 w-4" />, label: "Findings" },
      { key: "project-finding-review", icon: <ShieldCheck className="h-4 w-4" />, label: "Evidence Review" },
    ],
  },
  {
    key: "deliver",
    label: "Deliver",
    items: [
      { key: "project-reports", icon: <FileText className="h-4 w-4" />, label: "Reports" },
    ],
  },
  {
    key: "admin",
    label: "Runtime/Admin",
    items: [
      { key: "runtime", icon: <Network className="h-4 w-4" />, label: "Runtime" },
      { key: "runtime-readiness", icon: <ShieldCheck className="h-4 w-4" />, label: "Readiness" },
      { key: "runtime-sandbox", icon: <PlayCircle className="h-4 w-4" />, label: "Sandbox" },
      { key: "admin", icon: <ShieldCheck className="h-4 w-4" />, label: "Admin" },
    ],
  },
];

export const navigationItems: NavigationItem[] = navigationGroups.flatMap((group) => group.items);

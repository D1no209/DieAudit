import { Bot, Bug, FileText, FolderOpen, GitBranch, MessageSquareText, PlayCircle, ShieldCheck, Share2 } from "lucide-react";
import type { AppView } from "../navigation";
import { projectHash } from "../navigation";
import type { AuditRun, Project } from "../types";
import { Badge, Button } from "../ui";
import { statusTone } from "../utils/format";

type Props = {
  activeView: AppView;
  agentRunsCount: number;
  auditRun?: AuditRun;
  findingsCount: number;
  reportsCount: number;
  selectedProject?: Project;
  onViewChange: (view: AppView) => void;
};

const projectViews = new Set<AppView>([
  "project-overview",
  "project-audit-runs",
  "project-agents",
  "project-messages",
  "project-findings",
  "project-finding-review",
  "project-dependencies",
  "project-whiteboard",
  "project-swarm",
  "project-reports",
]);

export function AuditContextBar({
  activeView,
  agentRunsCount,
  auditRun,
  findingsCount,
  reportsCount,
  selectedProject,
}: Props) {
  if (!projectViews.has(activeView) && activeView !== "projects") return null;
  if (!selectedProject) {
    return (
      <section className="mb-5 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm shadow-slate-200/50" aria-label="Project workspace">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <ContextItem icon={<FolderOpen className="h-4 w-4" />} label="No project selected" />
          <Badge tone="warning">Select or import a project</Badge>
        </div>
      </section>
    );
  }

  const projectId = selectedProject.project_id;
  const auditRunId = auditRun?.audit_run_id;

  return (
    <section className="mb-5 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm shadow-slate-200/50" aria-label="Project workspace">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-5 gap-y-2 text-sm">
          <ContextItem icon={<FolderOpen className="h-4 w-4" />} label={selectedProject.name}>
            <Badge tone={statusTone(selectedProject.status)}>{selectedProject.status || "-"}</Badge>
          </ContextItem>
          <ContextItem icon={<PlayCircle className="h-4 w-4" />} label={auditRunId || "No audit run"}>
            <Badge tone={statusTone(auditRun?.status)}>{auditRun?.status || "-"}</Badge>
          </ContextItem>
          <ContextItem icon={<Bot className="h-4 w-4" />} label={`${agentRunsCount} agents`} />
          <ContextItem icon={<Bug className="h-4 w-4" />} label={`${findingsCount} findings`} />
          <ContextItem icon={<FileText className="h-4 w-4" />} label={`${reportsCount} reports`} />
        </div>
      </div>
      <nav className="mt-3 flex flex-wrap gap-2" aria-label="Project workspace navigation">
        <WorkspaceButton active={activeView === "project-overview"} href={projectHash("project-overview", projectId, auditRunId)} icon={<FolderOpen className="h-4 w-4" />} label="Project" />
        <WorkspaceButton active={activeView === "project-audit-runs"} href={projectHash("project-audit-runs", projectId, auditRunId)} icon={<PlayCircle className="h-4 w-4" />} label="Audit Runs" />
        <WorkspaceButton active={activeView === "project-agents"} disabled={!auditRunId} href={projectHash("project-agents", projectId, auditRunId)} icon={<Bot className="h-4 w-4" />} label="Agents" />
        <WorkspaceButton active={activeView === "project-messages"} disabled={!auditRunId} href={projectHash("project-messages", projectId, auditRunId)} icon={<MessageSquareText className="h-4 w-4" />} label="Messages" />
        <WorkspaceButton active={activeView === "project-whiteboard"} disabled={!auditRunId} href={projectHash("project-whiteboard", projectId, auditRunId)} icon={<GitBranch className="h-4 w-4" />} label="Whiteboard" />
        <WorkspaceButton active={activeView === "project-swarm"} disabled={!auditRunId} href={projectHash("project-swarm", projectId, auditRunId)} icon={<Share2 className="h-4 w-4" />} label="Swarm" />
        <WorkspaceButton active={activeView === "project-findings"} disabled={!auditRunId} href={projectHash("project-findings", projectId, auditRunId)} icon={<Bug className="h-4 w-4" />} label="Findings" />
        <WorkspaceButton active={activeView === "project-finding-review"} disabled={!auditRunId} href={projectHash("project-finding-review", projectId, auditRunId)} icon={<ShieldCheck className="h-4 w-4" />} label="Review" />
        <WorkspaceButton active={activeView === "project-reports"} disabled={!auditRunId} href={projectHash("project-reports", projectId, auditRunId)} icon={<FileText className="h-4 w-4" />} label="Reports" />
      </nav>
    </section>
  );
}

function WorkspaceButton({ active, disabled, href, icon, label }: { active: boolean; disabled?: boolean; href: string; icon: React.ReactNode; label: string }) {
  return (
    <Button
      size="sm"
      icon={icon}
      disabled={disabled}
      variant={active ? "primary" : "secondary"}
      onClick={() => {
        window.location.hash = href.replace(/^#/, "");
      }}
    >
      {label}
    </Button>
  );
}

function ContextItem({ children, icon, label }: { children?: React.ReactNode; icon: React.ReactNode; label: React.ReactNode }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-2 text-slate-600">
      <span className="text-slate-400">{icon}</span>
      <span className="max-w-[260px] truncate font-medium text-slate-800">{label}</span>
      {children}
    </span>
  );
}

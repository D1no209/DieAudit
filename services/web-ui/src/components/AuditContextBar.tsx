import { Bot, Bug, FileText, FolderOpen, PlayCircle, ShieldCheck } from "lucide-react";
import type { AppView } from "../navigation";
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

export function AuditContextBar({
  activeView,
  agentRunsCount,
  auditRun,
  findingsCount,
  reportsCount,
  selectedProject,
  onViewChange,
}: Props) {
  if (activeView === "overview") return null;

  return (
    <section className="mb-5 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm shadow-slate-200/50" aria-label="Audit context">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
          <ContextItem icon={<FolderOpen className="h-4 w-4" />} label={selectedProject?.name || "No project"}>
            <Badge tone={statusTone(selectedProject?.status)}>{selectedProject?.status || "-"}</Badge>
          </ContextItem>
          <ContextItem icon={<PlayCircle className="h-4 w-4" />} label={auditRun?.audit_run_id || "No audit run"}>
            <Badge tone={statusTone(auditRun?.status)}>{auditRun?.status || "-"}</Badge>
          </ContextItem>
          <ContextItem icon={<Bot className="h-4 w-4" />} label={`${agentRunsCount} agents`} />
          <ContextItem icon={<Bug className="h-4 w-4" />} label={`${findingsCount} findings`} />
          <ContextItem icon={<FileText className="h-4 w-4" />} label={`${reportsCount} reports`} />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" icon={<FolderOpen className="h-4 w-4" />} onClick={() => onViewChange("projects")}>Projects</Button>
          <Button size="sm" icon={<PlayCircle className="h-4 w-4" />} onClick={() => onViewChange("audit-runs")}>Audit</Button>
          <Button size="sm" icon={<Bug className="h-4 w-4" />} onClick={() => onViewChange("findings")}>Findings</Button>
          <Button size="sm" icon={<ShieldCheck className="h-4 w-4" />} onClick={() => onViewChange("finding-review")}>Review</Button>
          <Button size="sm" icon={<FileText className="h-4 w-4" />} onClick={() => onViewChange("reports")}>Reports</Button>
        </div>
      </div>
    </section>
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

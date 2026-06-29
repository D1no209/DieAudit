import type { AuditRun, PipelineStatus, Project } from "../../types";
import { Badge, MetricCard } from "../../ui";
import { statusTone } from "../../utils/format";

type Props = {
  agentRunsCount: number;
  auditRun?: AuditRun;
  pipelineStatus?: PipelineStatus;
  reportsCount: number;
  selectedProject?: Project;
};

export function AuditRunSummary({ agentRunsCount, auditRun, pipelineStatus, reportsCount, selectedProject }: Props) {
  return (
    <div className="mb-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="Project" value={selectedProject?.name || "-"} detail={selectedProject?.project_id || "No project selected"} />
      <MetricCard label="AuditRun" value={auditRun?.audit_run_id || "-"} detail={<Badge tone={statusTone(auditRun?.status)}>{auditRun?.status || "No run created"}</Badge>} />
      <MetricCard
        label="Pipeline"
        value={pipelineStatus?.current?.stage || "-"}
        detail={<Badge tone={statusTone(pipelineStatus?.current?.status)}>{pipelineStatus?.current?.status || "-"}</Badge>}
      />
      <MetricCard label="Reports" value={reportsCount} detail={`AgentRuns ${agentRunsCount}`} />
    </div>
  );
}

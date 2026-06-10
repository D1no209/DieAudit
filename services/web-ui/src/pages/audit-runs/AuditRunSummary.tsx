import { Card, Statistic, Tag, Typography } from "antd";
import type { AuditRun, PipelineStatus, Project } from "../../types";

const { Text } = Typography;

type Props = {
  agentRunsCount: number;
  auditRun?: AuditRun;
  pipelineStatus?: PipelineStatus;
  reportsCount: number;
  selectedProject?: Project;
};

export function AuditRunSummary({ agentRunsCount, auditRun, pipelineStatus, reportsCount, selectedProject }: Props) {
  return (
    <div className="run-summary-grid section">
      <Card>
        <Statistic title="Project" value={selectedProject?.name || "-"} />
        <Text type="secondary">{selectedProject?.project_id || "No project selected"}</Text>
      </Card>
      <Card>
        <Statistic title="AuditRun" value={auditRun?.audit_run_id || "-"} />
        <Text type="secondary">{auditRun?.status || "No run created"}</Text>
      </Card>
      <Card>
        <Statistic title="Pipeline" value={pipelineStatus?.current?.stage || "-"} />
        <Tag color={pipelineStatus?.current?.status === "failed" ? "red" : pipelineStatus?.current?.status === "completed" ? "green" : "blue"}>
          {pipelineStatus?.current?.status || "-"}
        </Tag>
      </Card>
      <Card>
        <Statistic title="Reports" value={reportsCount} />
        <Text type="secondary">AgentRuns {agentRunsCount}</Text>
      </Card>
    </div>
  );
}

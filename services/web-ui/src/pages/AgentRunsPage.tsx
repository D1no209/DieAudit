import { Alert, Card, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { AgentRun, AuditRun } from "../types";
import { PageHeader } from "../components/PageHeader";

const { Text } = Typography;

type Props = {
  agentColumns: ColumnsType<AgentRun>;
  agentRuns: AgentRun[];
  auditRun?: AuditRun;
};

export function AgentRunsPage({ agentColumns, agentRuns, auditRun }: Props) {
  return (
    <>
      <PageHeader title="Agent Runs" />
      {!auditRun && (
        <Alert
          className="section"
          type="info"
          showIcon
          message="No active AuditRun"
          description="Create an audit run before inspecting agent execution."
        />
      )}
      <Card
        className="section"
        title="Agent Execution"
        extra={
          <Text type="secondary">
            {auditRun?.audit_run_id || "No run"} {auditRun?.status ? <Tag>{auditRun.status}</Tag> : null}
          </Text>
        }
      >
        <Table rowKey="agent_run_id" columns={agentColumns} dataSource={agentRuns} pagination={{ pageSize: 10 }} />
      </Card>
    </>
  );
}

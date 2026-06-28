import { BranchesOutlined, CloudServerOutlined, NodeIndexOutlined, ProfileOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Empty, Row, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { AgentRun, AuditRun, ContainerRow, ExecutionGraph, ExecutionGraphNode } from "../types";
import { PageHeader } from "../components/PageHeader";

const { Paragraph, Text } = Typography;

type Props = {
  agentColumns: ColumnsType<AgentRun>;
  agentRuns: AgentRun[];
  auditRun?: AuditRun;
  containers: ContainerRow[];
  executionGraph?: ExecutionGraph;
  onOpenAgentEvents: (agentRunId: string) => void;
  onOpenContainerLogs: (row: ContainerRow) => void;
  onViewWhiteboard: () => void;
};

export function AgentRunsPage({
  agentColumns,
  agentRuns,
  auditRun,
  containers,
  executionGraph,
  onOpenAgentEvents,
  onOpenContainerLogs,
  onViewWhiteboard,
}: Props) {
  const nodes = executionGraph?.nodes || [];
  const edges = executionGraph?.edges || [];
  const runnableNodes = nodes.filter((node) =>
    ["agent-run", "whiteboard-task", "whiteboard-card", "container", "pipeline-step", "decompiled-artifact"].includes(node.kind),
  );
  const statusCounts = executionGraph?.summary?.by_status || {};
  const containerById = new Map(containers.map((container) => [container.Id || container.container_id || "", container]));

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
      <Row className="section" gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="Run Status">
            <Space wrap>
              <Tag color="green">completed {executionGraph?.summary?.completed ?? statusCounts.completed ?? 0}</Tag>
              <Tag color="blue">unfinished {executionGraph?.summary?.unfinished ?? 0}</Tag>
              <Tag color="red">failed {executionGraph?.summary?.failed ?? statusCounts.failed ?? 0}</Tag>
              <Tag icon={<BranchesOutlined />}>{edges.length} links</Tag>
            </Space>
            <Paragraph className="panel-description">
              Graph combines pipeline steps, ACP AgentRuns, containers, Whiteboard swarm tasks, and decompiled artifacts.
            </Paragraph>
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card
            title="Execution Graph"
            extra={
              <Space wrap>
                <Tag icon={<NodeIndexOutlined />}>{nodes.length} nodes</Tag>
                <Button size="small" onClick={onViewWhiteboard}>
                  Whiteboard
                </Button>
              </Space>
            }
          >
            {runnableNodes.length ? (
              <div className="agent-graph" aria-label="Agent execution graph">
                {runnableNodes.map((node) => (
                  <GraphNode
                    key={node.id}
                    node={node}
                    container={node.kind === "container" ? containerById.get(String(node.data?.container_id || "")) : undefined}
                    onOpenAgentEvents={onOpenAgentEvents}
                    onOpenContainerLogs={onOpenContainerLogs}
                    onViewWhiteboard={onViewWhiteboard}
                  />
                ))}
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No execution graph yet" />
            )}
          </Card>
        </Col>
      </Row>
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

function GraphNode({
  node,
  container,
  onOpenAgentEvents,
  onOpenContainerLogs,
  onViewWhiteboard,
}: {
  node: ExecutionGraphNode;
  container?: ContainerRow;
  onOpenAgentEvents: (agentRunId: string) => void;
  onOpenContainerLogs: (row: ContainerRow) => void;
  onViewWhiteboard: () => void;
}) {
  const color = statusColor(node.status);
  const icon =
    node.kind === "container"
      ? <CloudServerOutlined />
      : node.kind.startsWith("whiteboard")
        ? <BranchesOutlined />
        : <ProfileOutlined />;
  const agentRunId = node.target?.agent_run_id;
  return (
    <div className={`agent-graph-node agent-graph-node-${node.kind}`}>
      <Space align="start">
        <span className="agent-graph-icon">{icon}</span>
        <span>
          <Text strong>{node.label}</Text>
          <br />
          <Space wrap size={[4, 4]}>
            <Tag color={color}>{node.status || "unknown"}</Tag>
            <Tag>{node.kind}</Tag>
            {node.group ? <Tag>{node.group}</Tag> : null}
          </Space>
        </span>
      </Space>
      <Space wrap>
        {agentRunId ? (
          <Button size="small" onClick={() => onOpenAgentEvents(agentRunId)}>
            Events
          </Button>
        ) : null}
        {container ? (
          <Button size="small" onClick={() => onOpenContainerLogs(container)}>
            Logs
          </Button>
        ) : null}
        {node.kind.startsWith("whiteboard") ? (
          <Button size="small" onClick={onViewWhiteboard}>
            Open
          </Button>
        ) : null}
      </Space>
    </div>
  );
}

function statusColor(status?: string) {
  if (!status) {
    return "default";
  }
  if (["completed", "pass", "confirmed", "succeeded"].includes(status)) {
    return "green";
  }
  if (["failed", "cancelled", "false_positive"].includes(status)) {
    return "red";
  }
  if (["running", "starting", "queued", "open", "needs_agent", "agent_queued", "tracing"].includes(status)) {
    return "blue";
  }
  if (["skipped", "completed_with_warnings", "needs_review"].includes(status)) {
    return "orange";
  }
  return "default";
}

import { Alert, Card, List, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { RuntimeReadiness, RuntimeReadinessCheck, WorkerHeartbeat } from "../../types";
import { readinessColor, renderReadinessDescription } from "../../utils/format";

const { Text } = Typography;

type Props = {
  runtimeReadiness?: RuntimeReadiness;
  workerColumns: ColumnsType<WorkerHeartbeat>;
  workerHeartbeats: WorkerHeartbeat[];
};

type ReadinessListProps = {
  checks: RuntimeReadinessCheck[];
  emptyText: string;
};

function ReadinessList({ checks, emptyText }: ReadinessListProps) {
  if (checks.length === 0) {
    return <Alert type="success" showIcon message={emptyText} />;
  }

  return (
    <List
      dataSource={checks}
      renderItem={(item) => (
        <List.Item>
          <List.Item.Meta
            title={
              <Space>
                <Tag color={readinessColor(item.status)}>{item.status}</Tag>
                <Text>{item.title}</Text>
              </Space>
            }
            description={renderReadinessDescription(item)}
          />
        </List.Item>
      )}
    />
  );
}

export function RuntimeReadinessPanel({ runtimeReadiness, workerColumns, workerHeartbeats }: Props) {
  const blockingChecks = runtimeReadiness?.blocking_checks || (runtimeReadiness?.checks || []).filter((item) => item.status === "fail");
  const warningChecks = runtimeReadiness?.warning_checks || (runtimeReadiness?.checks || []).filter((item) => item.status === "warn");
  const allChecks = runtimeReadiness?.checks || [];

  return (
    <Card>
      <Space direction="vertical" size={16} className="drawer-stack">
        <Card size="small" title="Production Blockers">
          <ReadinessList checks={blockingChecks} emptyText="No blocking production readiness issues." />
        </Card>
        <Card size="small" title="Production Warnings">
          <ReadinessList checks={warningChecks} emptyText="No production readiness warnings." />
        </Card>
        <Card size="small" title={`All Checks (${allChecks.length})`}>
          <ReadinessList checks={allChecks} emptyText="No readiness checks reported." />
        </Card>
        <Table rowKey="worker_id" columns={workerColumns} dataSource={workerHeartbeats} pagination={false} size="small" />
      </Space>
    </Card>
  );
}

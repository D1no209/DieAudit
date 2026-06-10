import { Card, List, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { RuntimeReadiness, WorkerHeartbeat } from "../../types";
import { readinessColor, renderReadinessDescription } from "../../utils/format";

const { Text } = Typography;

type Props = {
  runtimeReadiness?: RuntimeReadiness;
  workerColumns: ColumnsType<WorkerHeartbeat>;
  workerHeartbeats: WorkerHeartbeat[];
};

export function RuntimeReadinessPanel({ runtimeReadiness, workerColumns, workerHeartbeats }: Props) {
  return (
    <Card>
      <Space direction="vertical" size={16} className="drawer-stack">
        <List
          dataSource={runtimeReadiness?.checks || []}
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
        <Table rowKey="worker_id" columns={workerColumns} dataSource={workerHeartbeats} pagination={false} size="small" />
      </Space>
    </Card>
  );
}

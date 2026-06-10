import { Card, List, Space, Tag, Typography } from "antd";
import type { PipelineStatus } from "../../types";

const { Text } = Typography;

type Props = {
  pipelineStatus?: PipelineStatus;
};

export function PipelineStatePanel({ pipelineStatus }: Props) {
  return (
    <Card title="Pipeline State">
      <Space direction="vertical" size={16} className="drawer-stack">
        <Space wrap>
          {Object.entries(pipelineStatus?.counts?.findings || {}).map(([status, count]) => (
            <Tag key={status}>
              {status}: {count}
            </Tag>
          ))}
          {Object.entries(pipelineStatus?.counts?.validation_attempts || {}).map(([status, count]) => (
            <Tag key={`attempt-${status}`}>
              attempt {status}: {count}
            </Tag>
          ))}
          <Tag>reports: {pipelineStatus?.counts?.reports ?? 0}</Tag>
        </Space>
        <List
          dataSource={pipelineStatus?.events || []}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <Tag>{item.event_type}</Tag>
                    <Text>{item.created_at}</Text>
                  </Space>
                }
                description={<pre>{JSON.stringify(item.payload || {}, null, 2)}</pre>}
              />
            </List.Item>
          )}
        />
      </Space>
    </Card>
  );
}

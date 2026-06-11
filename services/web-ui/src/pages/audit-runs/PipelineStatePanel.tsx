import { Alert, Card, List, Space, Tag, Typography } from "antd";
import type { PipelineStatus } from "../../types";

const { Text } = Typography;

type Props = {
  pipelineStatus?: PipelineStatus;
};

export function PipelineStatePanel({ pipelineStatus }: Props) {
  const warningEvents = (pipelineStatus?.events || []).filter((item) =>
    /warning|failed|unavailable|skipped|completed_with_warnings/i.test(item.event_type),
  );

  return (
    <Card title="Pipeline State">
      <Space direction="vertical" size={16} className="drawer-stack">
        {pipelineStatus?.current?.status === "completed_with_warnings" && (
          <Alert type="warning" showIcon message="Pipeline completed with warnings" />
        )}
        {warningEvents.length > 0 && (
          <Alert
            type="warning"
            showIcon
            message={`${warningEvents.length} warning or failure event(s) recorded`}
            description={warningEvents.slice(0, 3).map((item) => item.event_type).join(", ")}
          />
        )}
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

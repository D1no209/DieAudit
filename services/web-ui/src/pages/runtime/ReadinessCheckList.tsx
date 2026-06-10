import { Alert, List, Space, Tag, Typography } from "antd";
import type { RuntimeReadinessCheck } from "../../types";
import { readinessColor, renderReadinessDescription } from "../../utils/format";

const { Text } = Typography;

type Props = {
  checks: RuntimeReadinessCheck[];
  emptyText: string;
};

export function ReadinessCheckList({ checks, emptyText }: Props) {
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

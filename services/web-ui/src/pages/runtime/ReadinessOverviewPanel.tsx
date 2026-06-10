import { Card, Space, Statistic, Tag, Typography } from "antd";
import type { RuntimeReadiness } from "../../types";

const { Text } = Typography;

type Props = {
  runtimeReadiness?: RuntimeReadiness;
};

export function ReadinessOverviewPanel({ runtimeReadiness }: Props) {
  return (
    <Card title="Production Readiness">
      <Space direction="vertical" size={12} className="drawer-stack">
        <Space wrap>
          <Statistic title="Status" value={runtimeReadiness?.ok ? "Ready" : "Not Ready"} />
          <Statistic title="Blocking" value={runtimeReadiness?.summary?.fail ?? 0} />
          <Statistic title="Warnings" value={runtimeReadiness?.summary?.warn ?? 0} />
          <Statistic title="Passing" value={runtimeReadiness?.summary?.pass ?? 0} />
        </Space>
        <Space wrap>
          {(runtimeReadiness?.blocking_checks || []).slice(0, 4).map((item) => (
            <Tag key={item.id} color="red">
              {item.title}
            </Tag>
          ))}
        </Space>
        {!runtimeReadiness?.ok && (
          <Text type="secondary">Resolve blocking checks before exposing the platform beyond a trusted local deployment.</Text>
        )}
      </Space>
    </Card>
  );
}

import { Alert, Card, List, Typography } from "antd";
import type { RuntimeReadiness } from "../../types";

const { Text } = Typography;

type Props = {
  runtimeReadiness?: RuntimeReadiness;
};

export function ReadinessNextActionsPanel({ runtimeReadiness }: Props) {
  const actions = runtimeReadiness?.next_actions || [];

  if (!runtimeReadiness) {
    return (
      <Card title="Next Actions">
        <Alert type="warning" showIcon message="Readiness data is unavailable." />
      </Card>
    );
  }

  if (actions.length === 0) {
    return (
      <Card title="Next Actions">
        <Alert type="success" showIcon message="No production readiness actions are currently required." />
      </Card>
    );
  }

  return (
    <Card title="Next Actions">
      <List
        dataSource={actions}
        renderItem={(item, index) => (
          <List.Item>
            <List.Item.Meta
              title={`${index + 1}. ${item.title || item.id || "Readiness action"}`}
              description={
                <div className="readiness-remediation">
                  {(item.remediation || []).map((line) => (
                    <Text key={line} type="secondary">
                      {line}
                    </Text>
                  ))}
                </div>
              }
            />
          </List.Item>
        )}
      />
    </Card>
  );
}

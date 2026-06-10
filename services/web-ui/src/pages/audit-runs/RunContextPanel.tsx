import { Card, Collapse, Descriptions } from "antd";
import type { AuditRun, Project } from "../../types";

type Props = {
  auditRun?: AuditRun;
  lastResponse?: unknown;
  selectedProject?: Project;
};

export function RunContextPanel({ auditRun, lastResponse, selectedProject }: Props) {
  return (
    <Card title="Run Context">
      <Descriptions bordered size="small" column={1}>
        <Descriptions.Item label="Project">{selectedProject?.name || "-"}</Descriptions.Item>
        <Descriptions.Item label="Project ID">{selectedProject?.project_id || "-"}</Descriptions.Item>
        <Descriptions.Item label="AuditRun ID">{auditRun?.audit_run_id || "-"}</Descriptions.Item>
        <Descriptions.Item label="AuditRun Status">{auditRun?.status || "-"}</Descriptions.Item>
        <Descriptions.Item label="Created At">{auditRun?.created_at || "-"}</Descriptions.Item>
      </Descriptions>
      {Boolean(lastResponse) && (
        <Collapse
          className="table-toolbar"
          size="small"
          items={[
            {
              key: "last-response",
              label: "Last Response",
              children: <pre>{JSON.stringify(lastResponse, null, 2)}</pre>,
            },
          ]}
        />
      )}
    </Card>
  );
}

import { Card, Descriptions, Tag, Typography } from "antd";
import type { Project } from "../../types";

const { Text } = Typography;

type Props = {
  selectedProject?: Project;
};

export function SelectedProjectPanel({ selectedProject }: Props) {
  return (
    <Card title="Selected Project">
      <Descriptions bordered size="small" column={1}>
        <Descriptions.Item label="Name">{selectedProject?.name || "-"}</Descriptions.Item>
        <Descriptions.Item label="Project ID">{selectedProject?.project_id || "-"}</Descriptions.Item>
        <Descriptions.Item label="Source">{selectedProject?.source_type || "-"}</Descriptions.Item>
        <Descriptions.Item label="Status">
          {selectedProject?.status ? <Tag color={selectedProject.status === "ready" ? "green" : "blue"}>{selectedProject.status}</Tag> : "-"}
        </Descriptions.Item>
      </Descriptions>
      <Text type="secondary" className="block-hint">
        选择项目后，在 Audit Runs 页面启动审计闭环并查看运行结果。
      </Text>
    </Card>
  );
}

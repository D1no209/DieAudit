import { FileTextOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Button, Collapse, Descriptions, Drawer, List, Space, Tag, Typography } from "antd";
import type { ArtifactRef, FindingDetail } from "../../types";
import { severityColor } from "../../utils/format";

const { Text } = Typography;

type Props = {
  finding?: FindingDetail;
  loading: boolean;
  sandboxExecutionAvailable: boolean;
  sandboxUnavailableReason: string;
  onClose: () => void;
  onOpenArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onRunFindingPoc: () => void;
};

export function FindingDrawer({
  finding,
  loading,
  sandboxExecutionAvailable,
  sandboxUnavailableReason,
  onClose,
  onOpenArtifact,
  onRunFindingPoc,
}: Props) {
  return (
    <Drawer title={finding?.finding.title || "Finding"} open={Boolean(finding)} width={720} onClose={onClose}>
      {finding && (
        <Space direction="vertical" size={16} className="drawer-stack">
          <Space wrap>
            <Button
              icon={<SafetyCertificateOutlined />}
              loading={loading}
              disabled={!sandboxExecutionAvailable}
              title={sandboxExecutionAvailable ? undefined : sandboxUnavailableReason}
              onClick={onRunFindingPoc}
            >
              运行 PoC 验证
            </Button>
          </Space>
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="ID">{finding.finding.finding_id}</Descriptions.Item>
            <Descriptions.Item label="Severity">
              <Tag color={severityColor(finding.finding.severity)}>{finding.finding.severity}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Status">
              <Tag>{finding.finding.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Location">
              {finding.finding.file_path || "-"}:{finding.finding.line_start || "-"}
            </Descriptions.Item>
            <Descriptions.Item label="Source">{finding.finding.source}</Descriptions.Item>
            <Descriptions.Item label="Description">{finding.finding.description || "-"}</Descriptions.Item>
          </Descriptions>
          <Collapse
            items={[
              {
                key: "evidence",
                label: `Evidence (${finding.evidence.length})`,
                children: (
                  <List
                    dataSource={finding.evidence}
                    renderItem={(item) => (
                      <List.Item
                        actions={[
                          <Button
                            key="artifact"
                            size="small"
                            icon={<FileTextOutlined />}
                            disabled={!item.artifact && !item.artifact_path}
                            onClick={() => onOpenArtifact(item.artifact, item.artifact_path)}
                          >
                            下载
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          title={
                            <Space>
                              <Tag>{item.kind}</Tag>
                              <Text>{item.summary || item.artifact?.name || item.evidence_id}</Text>
                            </Space>
                          }
                          description={<pre>{JSON.stringify(item, null, 2)}</pre>}
                        />
                      </List.Item>
                    )}
                  />
                ),
              },
              {
                key: "attempts",
                label: `Validation Attempts (${finding.validation_attempts.length})`,
                children: <pre>{JSON.stringify(finding.validation_attempts, null, 2)}</pre>,
              },
              {
                key: "raw",
                label: "Raw",
                children: <pre>{JSON.stringify(finding.finding.raw || {}, null, 2)}</pre>,
              },
            ]}
          />
        </Space>
      )}
    </Drawer>
  );
}

import { FileTextOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Collapse, Descriptions, Empty, Form, Input, InputNumber, List, Space, Switch, Tag, Typography } from "antd";
import type { ArtifactRef, FindingDetail, SandboxPocFormValues } from "../../types";
import { severityColor } from "../../utils/format";

const { Text } = Typography;

type Props = {
  finding?: FindingDetail;
  loading: boolean;
  sandboxExecutionAvailable: boolean;
  sandboxUnavailableReason: string;
  onOpenArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onPreviewArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onRunFindingPoc: (values: SandboxPocFormValues) => void;
};

export function FindingDetailPanel({
  finding,
  loading,
  sandboxExecutionAvailable,
  sandboxUnavailableReason,
  onOpenArtifact,
  onPreviewArtifact,
  onRunFindingPoc,
}: Props) {
  if (!finding) {
    return (
      <Card className="section">
        <Empty
          description="Select a finding from the Findings page to review evidence, validation attempts, and PoC execution."
        />
      </Card>
    );
  }

  return (
    <Space direction="vertical" size={16} className="drawer-stack">
      {!sandboxExecutionAvailable && (
        <Alert type="warning" showIcon message="Sandbox execution is unavailable" description={sandboxUnavailableReason} />
      )}
      <Card title={finding.finding.title}>
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
          <Descriptions.Item label="Tracking Markdown">
            <Space wrap>
              <Text code>{finding.finding.finding_markdown?.relative_path || "-"}</Text>
              <Button
                size="small"
                icon={<FileTextOutlined />}
                disabled={!finding.finding.finding_markdown}
                onClick={() => onPreviewArtifact(finding.finding.finding_markdown)}
              >
                预览
              </Button>
              <Button
                size="small"
                icon={<FileTextOutlined />}
                disabled={!finding.finding.finding_markdown}
                onClick={() => onOpenArtifact(finding.finding.finding_markdown)}
              >
                打开
              </Button>
            </Space>
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Collapse
        defaultActiveKey={["evidence", "attempts"]}
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
                        key="preview"
                        size="small"
                        icon={<FileTextOutlined />}
                        disabled={!item.artifact && !item.artifact_path}
                        onClick={() => onPreviewArtifact(item.artifact, item.artifact_path)}
                      >
                        预览
                      </Button>,
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
            key: "poc",
            label: "PoC Execution",
            children: (
              <Form
                layout="vertical"
                initialValues={{
                  image: "python:3.12-slim",
                  expected_exit_code: 0,
                  mount_workspace: true,
                  retain_runtime_on_failure: false,
                  timeout_seconds: 120,
                }}
                onFinish={onRunFindingPoc}
              >
                <Form.Item name="image" label="Image" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
                <Form.Item name="command" label="Command" rules={[{ required: true }]}>
                  <Input.TextArea rows={5} placeholder={"python\n-c\nprint('project-specific PoC')"} />
                </Form.Item>
                <Space wrap>
                  <Form.Item name="timeout_seconds" label="Timeout">
                    <InputNumber min={1} max={3600} />
                  </Form.Item>
                  <Form.Item name="expected_exit_code" label="Expected Exit">
                    <InputNumber />
                  </Form.Item>
                </Space>
                <Space wrap>
                  <Form.Item name="mount_workspace" label="Mount Workspace" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name="retain_runtime_on_failure" label="Retain On Failure" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                </Space>
                <Button
                  icon={<SafetyCertificateOutlined />}
                  loading={loading}
                  htmlType="submit"
                  type="primary"
                  disabled={!sandboxExecutionAvailable}
                  title={sandboxExecutionAvailable ? undefined : sandboxUnavailableReason}
                >
                  Run PoC
                </Button>
              </Form>
            ),
          },
          {
            key: "raw",
            label: "Raw",
            children: <pre>{JSON.stringify(finding.finding.raw || {}, null, 2)}</pre>,
          },
        ]}
      />
    </Space>
  );
}

import { FileTextOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Button, Collapse, Descriptions, Drawer, List, Space, Tag, Typography } from "antd";
import type { ArtifactRef, FindingDetail } from "../types";
import { severityColor } from "../utils/format";

const { Text } = Typography;

type Props = {
  agentEvents?: Array<Record<string, unknown>>;
  containerLogs?: { title: string; body: string };
  loading: boolean;
  selectedFinding?: FindingDetail;
  onCloseAgentEvents: () => void;
  onCloseContainerLogs: () => void;
  onCloseFinding: () => void;
  onOpenArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onRunFindingPoc: () => void;
};

export function AppDrawers({
  agentEvents,
  containerLogs,
  loading,
  selectedFinding,
  onCloseAgentEvents,
  onCloseContainerLogs,
  onCloseFinding,
  onOpenArtifact,
  onRunFindingPoc,
}: Props) {
  return (
    <>
      <Drawer
        title={selectedFinding?.finding.title || "Finding"}
        open={Boolean(selectedFinding)}
        width={720}
        onClose={onCloseFinding}
      >
        {selectedFinding && (
          <Space direction="vertical" size={16} className="drawer-stack">
            <Space wrap>
              <Button icon={<SafetyCertificateOutlined />} loading={loading} onClick={onRunFindingPoc}>运行 PoC 验证</Button>
            </Space>
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label="ID">{selectedFinding.finding.finding_id}</Descriptions.Item>
              <Descriptions.Item label="Severity"><Tag color={severityColor(selectedFinding.finding.severity)}>{selectedFinding.finding.severity}</Tag></Descriptions.Item>
              <Descriptions.Item label="Status"><Tag>{selectedFinding.finding.status}</Tag></Descriptions.Item>
              <Descriptions.Item label="Location">{selectedFinding.finding.file_path || "-"}:{selectedFinding.finding.line_start || "-"}</Descriptions.Item>
              <Descriptions.Item label="Source">{selectedFinding.finding.source}</Descriptions.Item>
              <Descriptions.Item label="Description">{selectedFinding.finding.description || "-"}</Descriptions.Item>
            </Descriptions>
            <Collapse
              items={[
                {
                  key: "evidence",
                  label: `Evidence (${selectedFinding.evidence.length})`,
                  children: (
                    <List
                      dataSource={selectedFinding.evidence}
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
                            title={<Space><Tag>{item.kind}</Tag><Text>{item.summary || item.artifact?.name || item.evidence_id}</Text></Space>}
                            description={<pre>{JSON.stringify(item, null, 2)}</pre>}
                          />
                        </List.Item>
                      )}
                    />
                  ),
                },
                {
                  key: "attempts",
                  label: `Validation Attempts (${selectedFinding.validation_attempts.length})`,
                  children: <pre>{JSON.stringify(selectedFinding.validation_attempts, null, 2)}</pre>,
                },
                {
                  key: "raw",
                  label: "Raw",
                  children: <pre>{JSON.stringify(selectedFinding.finding.raw || {}, null, 2)}</pre>,
                },
              ]}
            />
          </Space>
        )}
      </Drawer>
      <Drawer
        title="Agent Events"
        open={Boolean(agentEvents)}
        width={720}
        onClose={onCloseAgentEvents}
      >
        <pre>{JSON.stringify(agentEvents || [], null, 2)}</pre>
      </Drawer>
      <Drawer
        title={`Container Logs - ${containerLogs?.title || ""}`}
        open={Boolean(containerLogs)}
        width={820}
        onClose={onCloseContainerLogs}
      >
        <pre>{containerLogs?.body || ""}</pre>
      </Drawer>
    </>
  );
}

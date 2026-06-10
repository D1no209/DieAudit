import { CloudServerOutlined, DeleteOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Button, Card, List, Space, Table, Tabs, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ContainerRow, RuntimeReadiness, WorkerHeartbeat } from "../types";
import { readinessColor, renderReadinessDescription } from "../utils/format";

const { Text } = Typography;

type Props = {
  containerColumns: ColumnsType<ContainerRow>;
  containers: ContainerRow[];
  loading: boolean;
  runtimeReadiness?: RuntimeReadiness;
  sandboxTarget?: { network: string; target_url: string };
  workerColumns: ColumnsType<WorkerHeartbeat>;
  workerHeartbeats: WorkerHeartbeat[];
  onCleanup: () => void;
  onCleanupExpiredRuntime: () => void;
  onRunPocSmoke: () => void;
  onRunSandboxTargetPoc: () => void;
  onStartSandboxService: () => void;
};

export function RuntimePage({
  containerColumns,
  containers,
  loading,
  runtimeReadiness,
  sandboxTarget,
  workerColumns,
  workerHeartbeats,
  onCleanup,
  onCleanupExpiredRuntime,
  onRunPocSmoke,
  onRunSandboxTargetPoc,
  onStartSandboxService,
}: Props) {
  return (
    <>
      <div className="action-bar section">
        <Button icon={<CloudServerOutlined />} loading={loading} onClick={onStartSandboxService}>Sandbox Service</Button>
        <Button icon={<SafetyCertificateOutlined />} loading={loading} disabled={!sandboxTarget} onClick={onRunSandboxTargetPoc}>Target PoC</Button>
        <Button icon={<SafetyCertificateOutlined />} loading={loading} onClick={onRunPocSmoke}>PoC Smoke</Button>
        <Button icon={<DeleteOutlined />} loading={loading} onClick={onCleanupExpiredRuntime}>清理过期运行时</Button>
        <Button danger icon={<DeleteOutlined />} loading={loading} onClick={onCleanup}>清理当前运行时</Button>
      </div>
      <Tabs
        className="section"
        items={[
          {
            key: "readiness",
            label: "Readiness",
            children: (
              <Card>
                <Space direction="vertical" size={16} className="drawer-stack">
                  <List
                    dataSource={runtimeReadiness?.checks || []}
                    renderItem={(item) => (
                      <List.Item>
                        <List.Item.Meta
                          title={<Space><Tag color={readinessColor(item.status)}>{item.status}</Tag><Text>{item.title}</Text></Space>}
                          description={renderReadinessDescription(item)}
                        />
                      </List.Item>
                    )}
                  />
                  <Table
                    rowKey="worker_id"
                    columns={workerColumns}
                    dataSource={workerHeartbeats}
                    pagination={false}
                    size="small"
                  />
                </Space>
              </Card>
            ),
          },
          { key: "containers", label: "Containers", children: <Card><Table rowKey="Id" columns={containerColumns} dataSource={containers} pagination={false} /></Card> },
        ]}
      />
    </>
  );
}

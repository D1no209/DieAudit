import { ClusterOutlined, PlayCircleOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Button, Card, Statistic } from "antd";
import type { AppView } from "../navigation";
import type { AuditRun, ContainerRow, RuntimeReadiness, SandboxCapabilities, WorkerHeartbeat } from "../types";
import { PageHeader } from "../components/PageHeader";
import { RuntimeActionBar } from "./runtime/RuntimeActionBar";

type Props = {
  auditRun?: AuditRun;
  containers: ContainerRow[];
  loading: boolean;
  runtimeReadiness?: RuntimeReadiness;
  sandboxCapabilities?: SandboxCapabilities;
  workerHeartbeats: WorkerHeartbeat[];
  onCleanup: () => void;
  onCleanupExpiredRuntime: () => void;
  onViewChange: (view: AppView) => void;
};

export function RuntimePage({
  auditRun,
  containers,
  loading,
  runtimeReadiness,
  sandboxCapabilities,
  workerHeartbeats,
  onCleanup,
  onCleanupExpiredRuntime,
  onViewChange,
}: Props) {
  const pageActions = (
    <RuntimeActionBar
      loading={loading}
      onCleanup={onCleanup}
      onCleanupExpiredRuntime={onCleanupExpiredRuntime}
    />
  );

  return (
    <>
      <PageHeader title="Runtime" actions={pageActions} />
      <div className="runtime-route-grid section">
        <Card
          title="Readiness"
          actions={[
            <Button key="open" type="link" icon={<SafetyCertificateOutlined />} onClick={() => onViewChange("runtime-readiness")}>
              打开
            </Button>,
          ]}
        >
          <Statistic title="Blocking Checks" value={runtimeReadiness?.summary?.fail ?? 0} />
        </Card>
        <Card
          title="Containers"
          actions={[
            <Button key="open" type="link" icon={<ClusterOutlined />} onClick={() => onViewChange("runtime-containers")}>
              打开
            </Button>,
          ]}
        >
          <Statistic title="Managed Containers" value={containers.length} />
        </Card>
        <Card
          title="Sandbox"
          actions={[
            <Button key="open" type="link" icon={<PlayCircleOutlined />} onClick={() => onViewChange("runtime-sandbox")}>
              打开
            </Button>,
          ]}
        >
          <Statistic title="Execution Available" value={sandboxCapabilities?.sandbox_execution_available ? "Yes" : "No"} />
        </Card>
        <Card title="Workers">
          <Statistic title="Heartbeats" value={workerHeartbeats.length} />
        </Card>
        <Card title="Active AuditRun">
          <Statistic title="Status" value={auditRun?.status || "None"} />
        </Card>
      </div>
    </>
  );
}

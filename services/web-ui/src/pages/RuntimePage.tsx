import { Alert, Tabs } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ContainerRow, RuntimeReadiness, SandboxCapabilities, WorkerHeartbeat } from "../types";
import { PageHeader } from "../components/PageHeader";
import { RuntimeActionBar } from "./runtime/RuntimeActionBar";
import { RuntimeContainersPanel } from "./runtime/RuntimeContainersPanel";
import { RuntimeReadinessPanel } from "./runtime/RuntimeReadinessPanel";

type Props = {
  containerColumns: ColumnsType<ContainerRow>;
  containers: ContainerRow[];
  loading: boolean;
  runtimeReadiness?: RuntimeReadiness;
  sandboxCapabilities?: SandboxCapabilities;
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
  sandboxCapabilities,
  sandboxTarget,
  workerColumns,
  workerHeartbeats,
  onCleanup,
  onCleanupExpiredRuntime,
  onRunPocSmoke,
  onRunSandboxTargetPoc,
  onStartSandboxService,
}: Props) {
  const sandboxExecutionAvailable = Boolean(sandboxCapabilities?.sandbox_execution_available);
  const sandboxUnavailableReason =
    sandboxCapabilities?.reason ||
    sandboxCapabilities?.warnings?.[0] ||
    "Sandbox execution is not available. Configure gVisor/Kata or another approved runtime before running PoC containers.";
  const pageActions = (
    <RuntimeActionBar
      loading={loading}
      sandboxExecutionAvailable={sandboxExecutionAvailable}
      sandboxTarget={sandboxTarget}
      onCleanup={onCleanup}
      onCleanupExpiredRuntime={onCleanupExpiredRuntime}
      onRunPocSmoke={onRunPocSmoke}
      onRunSandboxTargetPoc={onRunSandboxTargetPoc}
      onStartSandboxService={onStartSandboxService}
    />
  );

  return (
    <>
      <PageHeader title="Runtime" actions={pageActions} />
      {!sandboxExecutionAvailable && (
        <Alert
          className="section"
          type="warning"
          showIcon
          message="Sandbox execution is unavailable"
          description={sandboxUnavailableReason}
        />
      )}
      <Tabs
        className="section"
        items={[
          {
            key: "readiness",
            label: "Readiness",
            children: (
              <RuntimeReadinessPanel
                runtimeReadiness={runtimeReadiness}
                workerColumns={workerColumns}
                workerHeartbeats={workerHeartbeats}
              />
            ),
          },
          {
            key: "containers",
            label: "Containers",
            children: <RuntimeContainersPanel containerColumns={containerColumns} containers={containers} />,
          },
        ]}
      />
    </>
  );
}

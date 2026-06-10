import { Alert, Tabs } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ContainerRow, RuntimeReadiness, SandboxCapabilities, WorkerHeartbeat } from "../types";
import { PageHeader } from "../components/PageHeader";
import { RuntimeActionBar } from "./runtime/RuntimeActionBar";
import { RuntimeContainersPanel } from "./runtime/RuntimeContainersPanel";
import { RuntimeReadinessPanel } from "./runtime/RuntimeReadinessPanel";
import { RuntimeSandboxPanel } from "./runtime/RuntimeSandboxPanel";
import type { AuditRun, SandboxPocFormValues, SandboxServiceFormValues } from "../types";

type Props = {
  auditRun?: AuditRun;
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
  onRunSandboxPoc: (values: SandboxPocFormValues) => void;
  onRunSandboxTargetPoc: (values: SandboxPocFormValues) => void;
  onStartSandboxService: (values: SandboxServiceFormValues) => void;
};

export function RuntimePage({
  auditRun,
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
  onRunSandboxTargetPoc,
  onRunSandboxPoc,
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
      onCleanup={onCleanup}
      onCleanupExpiredRuntime={onCleanupExpiredRuntime}
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
          {
            key: "sandbox",
            label: "Sandbox",
            children: (
              <RuntimeSandboxPanel
                auditRun={auditRun}
                loading={loading}
                sandboxCapabilities={sandboxCapabilities}
                sandboxTarget={sandboxTarget}
                sandboxUnavailableReason={sandboxUnavailableReason}
                onRunSandboxPoc={onRunSandboxPoc}
                onRunSandboxTargetPoc={onRunSandboxTargetPoc}
                onStartSandboxService={onStartSandboxService}
              />
            ),
          },
        ]}
      />
    </>
  );
}

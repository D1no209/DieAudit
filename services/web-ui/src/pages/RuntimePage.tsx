import { Boxes, PlayCircle, ShieldCheck } from "lucide-react";
import type { AppView } from "../navigation";
import type { AuditRun, ContainerRow, RuntimeReadiness, SandboxCapabilities, WorkerHeartbeat } from "../types";
import { Button, MetricCard, PageHeader } from "../ui";
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
  const pageActions = <RuntimeActionBar loading={loading} onCleanup={onCleanup} onCleanupExpiredRuntime={onCleanupExpiredRuntime} />;

  return (
    <>
      <PageHeader title="Runtime" actions={pageActions} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <MetricCard
          label="Readiness"
          value={runtimeReadiness?.summary?.fail ?? 0}
          detail={<Button size="sm" variant="link" icon={<ShieldCheck className="h-4 w-4" />} onClick={() => onViewChange("runtime-readiness")}>打开</Button>}
        />
        <MetricCard
          label="Containers"
          value={containers.length}
          detail={<Button size="sm" variant="link" icon={<Boxes className="h-4 w-4" />} onClick={() => onViewChange("runtime-containers")}>打开</Button>}
        />
        <MetricCard
          label="Sandbox"
          value={sandboxCapabilities?.sandbox_execution_available ? "Yes" : "No"}
          detail={<Button size="sm" variant="link" icon={<PlayCircle className="h-4 w-4" />} onClick={() => onViewChange("runtime-sandbox")}>打开</Button>}
        />
        <MetricCard label="Workers" value={workerHeartbeats.length} detail="Heartbeats" />
        <MetricCard label="Active AuditRun" value={auditRun?.status || "None"} />
      </div>
    </>
  );
}

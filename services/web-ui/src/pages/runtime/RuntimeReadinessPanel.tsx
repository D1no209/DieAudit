import { Card, Space } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { RuntimeReadiness, RuntimeReadinessCheck, WorkerHeartbeat } from "../../types";
import { ReadinessCheckList } from "./ReadinessCheckList";
import { ReadinessNextActionsPanel } from "./ReadinessNextActionsPanel";
import { ReadinessOverviewPanel } from "./ReadinessOverviewPanel";
import { WorkerHeartbeatPanel } from "./WorkerHeartbeatPanel";

type Props = {
  runtimeReadiness?: RuntimeReadiness;
  workerColumns: ColumnsType<WorkerHeartbeat>;
  workerHeartbeats: WorkerHeartbeat[];
};

export function RuntimeReadinessPanel({ runtimeReadiness, workerColumns, workerHeartbeats }: Props) {
  const blockingChecks = runtimeReadiness?.blocking_checks || (runtimeReadiness?.checks || []).filter((item) => item.status === "fail");
  const warningChecks = runtimeReadiness?.warning_checks || (runtimeReadiness?.checks || []).filter((item) => item.status === "warn");
  const allChecks = runtimeReadiness?.checks || [];
  const emptyBlockersText = runtimeReadiness
    ? "No blocking production readiness issues."
    : "Readiness data is unavailable; refresh after API access is configured.";
  const emptyWarningsText = runtimeReadiness
    ? "No production readiness warnings."
    : "Readiness data is unavailable; refresh after API access is configured.";
  const emptyChecksText = runtimeReadiness
    ? "No readiness checks reported."
    : "Readiness data is unavailable; refresh after API access is configured.";

  return (
    <Space direction="vertical" size={16} className="drawer-stack">
      <ReadinessOverviewPanel runtimeReadiness={runtimeReadiness} />
      <ReadinessNextActionsPanel runtimeReadiness={runtimeReadiness} />
      <Card title="Production Blockers">
        <ReadinessCheckList checks={blockingChecks} emptyText={emptyBlockersText} type={runtimeReadiness ? "success" : "warning"} />
      </Card>
      <Card title="Production Warnings">
        <ReadinessCheckList checks={warningChecks} emptyText={emptyWarningsText} type={runtimeReadiness ? "success" : "warning"} />
      </Card>
      <Card title={`All Checks (${allChecks.length})`}>
        <ReadinessCheckList checks={allChecks} emptyText={emptyChecksText} type={runtimeReadiness ? "success" : "warning"} />
      </Card>
      <WorkerHeartbeatPanel workerColumns={workerColumns} workerHeartbeats={workerHeartbeats} />
    </Space>
  );
}

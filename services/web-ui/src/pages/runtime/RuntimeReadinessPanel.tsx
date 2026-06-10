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

  return (
    <Space direction="vertical" size={16} className="drawer-stack">
      <ReadinessOverviewPanel runtimeReadiness={runtimeReadiness} />
      <ReadinessNextActionsPanel runtimeReadiness={runtimeReadiness} />
      <Card title="Production Blockers">
        <ReadinessCheckList checks={blockingChecks} emptyText="No blocking production readiness issues." />
      </Card>
      <Card title="Production Warnings">
        <ReadinessCheckList checks={warningChecks} emptyText="No production readiness warnings." />
      </Card>
      <Card title={`All Checks (${allChecks.length})`}>
        <ReadinessCheckList checks={allChecks} emptyText="No readiness checks reported." />
      </Card>
      <WorkerHeartbeatPanel workerColumns={workerColumns} workerHeartbeats={workerHeartbeats} />
    </Space>
  );
}

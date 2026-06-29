import type { RuntimeReadiness, WorkerHeartbeat } from "../../types";
import { Panel, type DataColumn } from "../../ui";
import { ReadinessCheckList } from "./ReadinessCheckList";
import { ReadinessNextActionsPanel } from "./ReadinessNextActionsPanel";
import { ReadinessOverviewPanel } from "./ReadinessOverviewPanel";
import { WorkerHeartbeatPanel } from "./WorkerHeartbeatPanel";

type Props = {
  runtimeReadiness?: RuntimeReadiness;
  workerColumns: DataColumn<WorkerHeartbeat>[];
  workerHeartbeats: WorkerHeartbeat[];
};

export function RuntimeReadinessPanel({ runtimeReadiness, workerColumns, workerHeartbeats }: Props) {
  const blockingChecks = runtimeReadiness?.blocking_checks || (runtimeReadiness?.checks || []).filter((item) => item.status === "fail");
  const warningChecks = runtimeReadiness?.warning_checks || (runtimeReadiness?.checks || []).filter((item) => item.status === "warn");
  const allChecks = runtimeReadiness?.checks || [];
  const emptyBlockersText = runtimeReadiness ? "No blocking production readiness issues." : "Readiness data is unavailable; refresh after API access is configured.";
  const emptyWarningsText = runtimeReadiness ? "No production readiness warnings." : "Readiness data is unavailable; refresh after API access is configured.";
  const emptyChecksText = runtimeReadiness ? "No readiness checks reported." : "Readiness data is unavailable; refresh after API access is configured.";

  return (
    <div className="grid gap-4">
      <ReadinessOverviewPanel runtimeReadiness={runtimeReadiness} />
      <ReadinessNextActionsPanel runtimeReadiness={runtimeReadiness} />
      <Panel title="Production Blockers">
        <ReadinessCheckList checks={blockingChecks} emptyText={emptyBlockersText} type={runtimeReadiness ? "success" : "warning"} />
      </Panel>
      <Panel title="Production Warnings">
        <ReadinessCheckList checks={warningChecks} emptyText={emptyWarningsText} type={runtimeReadiness ? "success" : "warning"} />
      </Panel>
      <Panel title={`All Checks (${allChecks.length})`}>
        <ReadinessCheckList checks={allChecks} emptyText={emptyChecksText} type={runtimeReadiness ? "success" : "warning"} />
      </Panel>
      <WorkerHeartbeatPanel workerColumns={workerColumns} workerHeartbeats={workerHeartbeats} />
    </div>
  );
}

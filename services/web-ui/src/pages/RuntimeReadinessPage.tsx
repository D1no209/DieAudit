import type { RuntimeReadiness, WorkerHeartbeat } from "../types";
import type { DataColumn } from "../ui";
import { PageHeader } from "../components/PageHeader";
import { RuntimeReadinessPanel } from "./runtime/RuntimeReadinessPanel";

type Props = {
  runtimeReadiness?: RuntimeReadiness;
  workerColumns: DataColumn<WorkerHeartbeat>[];
  workerHeartbeats: WorkerHeartbeat[];
};

export function RuntimeReadinessPage({ runtimeReadiness, workerColumns, workerHeartbeats }: Props) {
  return (
    <>
      <PageHeader title="Runtime Readiness" />
      <RuntimeReadinessPanel
        runtimeReadiness={runtimeReadiness}
        workerColumns={workerColumns}
        workerHeartbeats={workerHeartbeats}
      />
    </>
  );
}

import type { ColumnsType } from "antd/es/table";
import type { RuntimeReadiness, WorkerHeartbeat } from "../types";
import { PageHeader } from "../components/PageHeader";
import { RuntimeReadinessPanel } from "./runtime/RuntimeReadinessPanel";

type Props = {
  runtimeReadiness?: RuntimeReadiness;
  workerColumns: ColumnsType<WorkerHeartbeat>;
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

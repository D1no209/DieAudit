import type { WorkerHeartbeat } from "../../types";
import { DataTable, Panel, type DataColumn } from "../../ui";

type Props = {
  workerColumns: DataColumn<WorkerHeartbeat>[];
  workerHeartbeats: WorkerHeartbeat[];
};

export function WorkerHeartbeatPanel({ workerColumns, workerHeartbeats }: Props) {
  return (
    <Panel title="Workflow Workers">
      <DataTable getRowKey={(row) => row.worker_id} columns={workerColumns} data={workerHeartbeats} pagination={false} />
    </Panel>
  );
}

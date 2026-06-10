import { Card, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { WorkerHeartbeat } from "../../types";

type Props = {
  workerColumns: ColumnsType<WorkerHeartbeat>;
  workerHeartbeats: WorkerHeartbeat[];
};

export function WorkerHeartbeatPanel({ workerColumns, workerHeartbeats }: Props) {
  return (
    <Card title="Workflow Workers">
      <Table rowKey="worker_id" columns={workerColumns} dataSource={workerHeartbeats} pagination={false} size="small" />
    </Card>
  );
}

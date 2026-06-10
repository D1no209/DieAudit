import { Card, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Finding } from "../types";

type Props = {
  findingColumns: ColumnsType<Finding>;
  findings: Finding[];
};

export function FindingsPage({ findingColumns, findings }: Props) {
  return (
    <Card className="section">
      <Table rowKey="finding_id" columns={findingColumns} dataSource={findings} pagination={{ pageSize: 8 }} />
    </Card>
  );
}

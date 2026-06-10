import { Card, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ContainerRow } from "../../types";

type Props = {
  containerColumns: ColumnsType<ContainerRow>;
  containers: ContainerRow[];
};

export function RuntimeContainersPanel({ containerColumns, containers }: Props) {
  return (
    <Card>
      <Table rowKey="Id" columns={containerColumns} dataSource={containers} pagination={false} />
    </Card>
  );
}

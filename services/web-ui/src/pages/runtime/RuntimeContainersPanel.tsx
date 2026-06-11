import { Alert, Card, Space, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ContainerRow } from "../../types";

type Props = {
  containerColumns: ColumnsType<ContainerRow>;
  containers: ContainerRow[];
};

export function RuntimeContainersPanel({ containerColumns, containers }: Props) {
  const retained = containers.filter((item) => item.State !== "removed" && item.db_status !== "removed");

  return (
    <Space direction="vertical" size={16} className="drawer-stack">
      {retained.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message="Runtime containers are retained"
          description={`${retained.length} managed container(s) are still present. This is expected when retain_runtime_on_failure is enabled or a sandbox target is running.`}
        />
      )}
      <Card>
        <Table rowKey="Id" columns={containerColumns} dataSource={containers} pagination={false} />
      </Card>
    </Space>
  );
}

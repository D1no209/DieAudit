import { Badge, Card, Space, Statistic, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { DependencyInventory, DependencyRecord } from "../types";
import { PageHeader } from "../components/PageHeader";

const { Text } = Typography;

type Props = {
  dependencies?: DependencyInventory;
};

export function DependenciesPage({ dependencies }: Props) {
  const dependencyColumns: ColumnsType<DependencyRecord> = [
    { title: "Ecosystem", dataIndex: "ecosystem", width: 130, render: (value) => <Tag>{value}</Tag> },
    { title: "Package", dataIndex: "name", ellipsis: true },
    { title: "Version", dataIndex: "version", width: 150, render: (value) => value || "-" },
    { title: "Manifest", dataIndex: "manifest", ellipsis: true, render: (value) => value || "-" },
    {
      title: "Vulns",
      dataIndex: "vulnerability_count",
      width: 110,
      render: (value) => <Badge count={value} color={value > 0 ? "#cf1322" : "#52c41a"} showZero />,
    },
  ];
  const byEcosystem = Object.entries(dependencies?.summary.by_ecosystem || {});

  return (
    <>
      <PageHeader title="Dependencies" />
      <div className="stats-grid section">
        <Card><Statistic title="Packages" value={dependencies?.summary.total ?? 0} /></Card>
        <Card><Statistic title="Vulnerable" value={dependencies?.summary.vulnerable ?? 0} /></Card>
        <Card>
          <Statistic title="Ecosystems" value={byEcosystem.length} />
          <Space wrap>
            {byEcosystem.map(([name, count]) => (
              <Tag key={name}>{name}: {count}</Tag>
            ))}
            {byEcosystem.length === 0 && <Text type="secondary">No dependency inventory yet</Text>}
          </Space>
        </Card>
      </div>
      <Card className="section" title="Dependency Inventory">
        <Table
          rowKey="dependency_id"
          columns={dependencyColumns}
          dataSource={dependencies?.packages || []}
          pagination={{ pageSize: 10 }}
        />
      </Card>
    </>
  );
}

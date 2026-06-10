import { Badge, Button, Card, Space, Statistic, Table, Tabs, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { DependencyRecord, DependencyInventory, Finding } from "../types";
import { severityColor } from "../utils/format";

const { Text } = Typography;

type Props = {
  dependencies?: DependencyInventory;
  findings: Finding[];
  onOpenFinding: (findingId: string) => void;
};

export function FindingsPage({ dependencies, findings, onOpenFinding }: Props) {
  const findingColumns: ColumnsType<Finding> = [
    { title: "Title", dataIndex: "title", ellipsis: true },
    { title: "Severity", dataIndex: "severity", width: 110, render: (value) => <Tag color={severityColor(value)}>{value}</Tag> },
    { title: "Status", dataIndex: "status", width: 130 },
    { title: "Path", dataIndex: "file_path", ellipsis: true, render: (value) => value || "-" },
    { title: "Rule", dataIndex: "rule_id", width: 170, ellipsis: true, render: (value) => value || "-" },
    { title: "Source", dataIndex: "source", width: 120 },
    {
      title: "Detail",
      width: 100,
      render: (_, row) => (
        <Button size="small" type="link" onClick={() => onOpenFinding(row.finding_id)}>研判</Button>
      ),
    },
  ];

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
    <Tabs
      className="section"
      items={[
        {
          key: "findings",
          label: `Findings (${findings.length})`,
          children: (
            <Card>
              <Table rowKey="finding_id" columns={findingColumns} dataSource={findings} pagination={{ pageSize: 8 }} />
            </Card>
          ),
        },
        {
          key: "dependencies",
          label: `Dependencies (${dependencies?.summary.total ?? 0})`,
          children: (
            <Space direction="vertical" size={16} className="drawer-stack">
              <div className="stats-grid">
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
              <Card>
                <Table
                  rowKey="dependency_id"
                  columns={dependencyColumns}
                  dataSource={dependencies?.packages || []}
                  pagination={{ pageSize: 10 }}
                />
              </Card>
            </Space>
          ),
        },
      ]}
    />
  );
}

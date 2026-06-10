import { Button, Card, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Finding } from "../types";
import { severityColor } from "../utils/format";
import { PageHeader } from "../components/PageHeader";

type Props = {
  findings: Finding[];
  onOpenFinding: (findingId: string) => void;
};

export function FindingsPage({ findings, onOpenFinding }: Props) {
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
        <Button size="small" type="link" onClick={() => onOpenFinding(row.finding_id)}>打开研判</Button>
      ),
    },
  ];

  return (
    <>
      <PageHeader title="Findings" />
      <Card className="section" title={`Findings (${findings.length})`}>
        <Table rowKey="finding_id" columns={findingColumns} dataSource={findings} pagination={{ pageSize: 10 }} />
      </Card>
    </>
  );
}

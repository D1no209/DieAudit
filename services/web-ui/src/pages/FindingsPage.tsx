import type { Finding } from "../types";
import { Badge, Button, DataTable, Panel, type DataColumn } from "../ui";
import { severityTone } from "../displayMeta";
import { statusTone } from "../utils/format";
import { PageHeader } from "../components/PageHeader";

type Props = {
  findings: Finding[];
  onOpenFinding: (findingId: string) => void;
};

export function FindingsPage({ findings, onOpenFinding }: Props) {
  const severityFilters = Array.from(new Set(findings.map((item) => item.severity).filter(Boolean)));
  const statusFilters = Array.from(new Set(findings.map((item) => item.status).filter(Boolean)));
  const sourceFilters = Array.from(new Set(findings.map((item) => item.source).filter(Boolean)));
  const findingColumns: DataColumn<Finding>[] = [
    { title: "Title", dataIndex: "title" },
    { title: "Severity", dataIndex: "severity", width: 110, render: (value) => <Badge tone={severityTone(String(value))}>{String(value || "-")}</Badge> },
    { title: "Status", dataIndex: "status", width: 150, render: (value) => <Badge tone={statusTone(String(value))}>{String(value || "-")}</Badge> },
    { title: "Path", dataIndex: "file_path", render: (value) => String(value || "-") },
    { title: "Rule", dataIndex: "rule_id", width: 170, render: (value) => String(value || "-") },
    { title: "Source", dataIndex: "source", width: 140, render: (value) => <Badge>{String(value || "-")}</Badge> },
    { title: "Detail", width: 120, render: (_, row) => <Button size="sm" variant="link" onClick={() => onOpenFinding(row.finding_id)}>打开研判</Button> },
  ];

  return (
    <>
      <PageHeader title="Findings" eyebrow="Validate" />
      <Panel
        title={`Findings (${findings.length})`}
        actions={
          <div className="hidden gap-1 md:flex">
            <Badge>severity {severityFilters.length}</Badge>
            <Badge>status {statusFilters.length}</Badge>
            <Badge>source {sourceFilters.length}</Badge>
          </div>
        }
      >
        <DataTable getRowKey={(row) => row.finding_id} columns={findingColumns} data={findings} pagination={{ pageSize: 10 }} />
      </Panel>
    </>
  );
}

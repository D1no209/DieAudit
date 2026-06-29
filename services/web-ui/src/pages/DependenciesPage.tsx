import type { DependencyInventory, DependencyRecord } from "../types";
import { Badge, DataTable, MetricCard, Panel, type DataColumn } from "../ui";
import { PageHeader } from "../components/PageHeader";

type Props = {
  dependencies?: DependencyInventory;
};

export function DependenciesPage({ dependencies }: Props) {
  const dependencyColumns: DataColumn<DependencyRecord>[] = [
    { title: "Ecosystem", dataIndex: "ecosystem", width: 130, render: (value) => <Badge>{String(value || "-")}</Badge> },
    { title: "Package", dataIndex: "name" },
    { title: "Version", dataIndex: "version", width: 150, render: (value) => String(value || "-") },
    { title: "Manifest", dataIndex: "manifest", render: (value) => String(value || "-") },
    { title: "Vulns", dataIndex: "vulnerability_count", width: 110, render: (value) => <Badge tone={Number(value) > 0 ? "danger" : "success"}>{String(value ?? 0)}</Badge> },
  ];
  const byEcosystem = Object.entries(dependencies?.summary.by_ecosystem || {});

  return (
    <>
      <PageHeader title="Dependencies" />
      <div className="mb-5 grid gap-4 md:grid-cols-3">
        <MetricCard label="Packages" value={dependencies?.summary.total ?? 0} />
        <MetricCard label="Vulnerable" value={dependencies?.summary.vulnerable ?? 0} />
        <MetricCard
          label="Ecosystems"
          value={byEcosystem.length}
          detail={
            <span className="flex flex-wrap gap-1">
              {byEcosystem.map(([name, count]) => <Badge key={name}>{name}: {count}</Badge>)}
              {byEcosystem.length === 0 ? <span>No dependency inventory yet</span> : null}
            </span>
          }
        />
      </div>
      <Panel title="Dependency Inventory">
        <DataTable getRowKey={(row) => row.dependency_id} columns={dependencyColumns} data={dependencies?.packages || []} pagination={{ pageSize: 10 }} />
      </Panel>
    </>
  );
}

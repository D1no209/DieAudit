import type { Project } from "../../types";
import type { DataColumn } from "../../ui";
import { DataTable, Panel } from "../../ui";

type Props = {
  projectColumns: DataColumn<Project>[];
  projects: Project[];
  selectedProjectId?: string;
  onSelectProject: (projectId: string) => void;
};

export function ProjectInventoryTable({ projectColumns, projects, selectedProjectId, onSelectProject }: Props) {
  return (
    <Panel title="Project Inventory">
      <DataTable
        getRowKey={(row) => row.project_id}
        columns={projectColumns}
        data={projects}
        pagination={{ pageSize: 10 }}
        selectedRowKey={selectedProjectId}
        onRowClick={(row) => onSelectProject(row.project_id)}
      />
    </Panel>
  );
}

import { Card, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Project } from "../../types";

type Props = {
  projectColumns: ColumnsType<Project>;
  projects: Project[];
  selectedProjectId?: string;
  onSelectProject: (projectId: string) => void;
};

export function ProjectInventoryTable({ projectColumns, projects, selectedProjectId, onSelectProject }: Props) {
  return (
    <Card className="section" title="Project Inventory">
      <Table
        rowKey="project_id"
        size="small"
        columns={projectColumns}
        dataSource={projects}
        pagination={{ pageSize: 10 }}
        rowSelection={{
          type: "radio",
          selectedRowKeys: selectedProjectId ? [selectedProjectId] : [],
          onChange: ([key]) => onSelectProject(String(key)),
        }}
      />
    </Card>
  );
}

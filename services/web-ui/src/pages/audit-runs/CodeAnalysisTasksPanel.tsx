import type { CodeAnalysisTask } from "../../types";
import { Badge, DataTable, EmptyState, Panel, type DataColumn } from "../../ui";
import { statusTone } from "../../utils/format";

type Props = {
  tasks: CodeAnalysisTask[];
};

export function CodeAnalysisTasksPanel({ tasks }: Props) {
  const columns: DataColumn<CodeAnalysisTask>[] = [
    { title: "Focus", dataIndex: "focus", width: 180, render: (value) => <Badge>{String(value || "-")}</Badge> },
    { title: "Status", dataIndex: "status", width: 120, render: (value) => <Badge tone={statusTone(String(value))}>{String(value || "-")}</Badge> },
    {
      title: "Files",
      render: (_, row) => (
        <span className="grid gap-1">
          <span>{row.file_paths.length} files</span>
          <span className="truncate text-xs text-slate-500">{row.file_paths.slice(0, 4).join(", ")}</span>
        </span>
      ),
    },
    { title: "AgentRun", dataIndex: "agent_run_id", width: 260, render: (value) => <code className="text-xs">{String(value || "-")}</code> },
  ];

  return (
    <Panel title={`Code Batch Analysis (${tasks.length})`}>
      {tasks.length === 0 ? (
        <EmptyState description="No code analysis tasks have been planned." />
      ) : (
        <DataTable getRowKey={(row) => row.task_id} columns={columns} data={tasks} pagination={{ pageSize: 6 }} />
      )}
    </Panel>
  );
}

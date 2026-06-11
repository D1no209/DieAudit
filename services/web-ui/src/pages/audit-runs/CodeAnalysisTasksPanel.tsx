import { Card, Empty, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { CodeAnalysisTask } from "../../types";

const { Text } = Typography;

type Props = {
  tasks: CodeAnalysisTask[];
};

const statusColor: Record<string, string> = {
  completed: "green",
  created: "default",
  failed: "red",
  running: "blue",
};

export function CodeAnalysisTasksPanel({ tasks }: Props) {
  const columns: ColumnsType<CodeAnalysisTask> = [
    {
      title: "Focus",
      dataIndex: "focus",
      key: "focus",
      width: 180,
      render: (value: string) => <Tag>{value}</Tag>,
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 120,
      render: (value: string) => <Tag color={statusColor[value] || "default"}>{value}</Tag>,
    },
    {
      title: "Files",
      key: "files",
      render: (_, row) => (
        <Space direction="vertical" size={2}>
          <Text>{row.file_paths.length} files</Text>
          <Text type="secondary" ellipsis>
            {row.file_paths.slice(0, 4).join(", ")}
          </Text>
        </Space>
      ),
    },
    {
      title: "AgentRun",
      dataIndex: "agent_run_id",
      key: "agent_run_id",
      width: 260,
      render: (value?: string) => <Text code>{value || "-"}</Text>,
    },
  ];

  return (
    <Card className="section" title={`Code Batch Analysis (${tasks.length})`}>
      {tasks.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No code analysis tasks have been planned." />
      ) : (
        <Table rowKey="task_id" size="small" pagination={{ pageSize: 6 }} columns={columns} dataSource={tasks} />
      )}
    </Card>
  );
}

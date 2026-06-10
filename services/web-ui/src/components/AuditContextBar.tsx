import {
  BugOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { Button, Flex, Space, Tag, Typography } from "antd";
import type { AppView } from "../navigation";
import type { AuditRun, Project } from "../types";

const { Text } = Typography;

type Props = {
  activeView: AppView;
  agentRunsCount: number;
  auditRun?: AuditRun;
  findingsCount: number;
  reportsCount: number;
  selectedProject?: Project;
  onViewChange: (view: AppView) => void;
};

function statusColor(status?: string) {
  if (!status) {
    return "default";
  }
  if (["completed", "confirmed", "ready"].includes(status)) {
    return "green";
  }
  if (["failed", "cancelled", "false_positive"].includes(status)) {
    return "red";
  }
  if (["running", "validating", "queued"].includes(status)) {
    return "blue";
  }
  return "default";
}

export function AuditContextBar({
  activeView,
  agentRunsCount,
  auditRun,
  findingsCount,
  reportsCount,
  selectedProject,
  onViewChange,
}: Props) {
  if (activeView === "overview") {
    return null;
  }

  return (
    <section className="audit-context-bar" aria-label="Audit context">
      <Flex align="center" justify="space-between" gap={16} wrap>
        <Space size={18} wrap>
          <Space size={8}>
            <FolderOpenOutlined />
            <Text strong>{selectedProject?.name || "No project"}</Text>
            <Tag>{selectedProject?.status || "-"}</Tag>
          </Space>
          <Space size={8}>
            <PlayCircleOutlined />
            <Text copyable={Boolean(auditRun?.audit_run_id)}>{auditRun?.audit_run_id || "No audit run"}</Text>
            <Tag color={statusColor(auditRun?.status)}>{auditRun?.status || "-"}</Tag>
          </Space>
          <Space size={8}>
            <RobotOutlined />
            <Text type="secondary">{agentRunsCount} agents</Text>
          </Space>
          <Space size={8}>
            <BugOutlined />
            <Text type="secondary">{findingsCount} findings</Text>
          </Space>
          <Space size={8}>
            <FileTextOutlined />
            <Text type="secondary">{reportsCount} reports</Text>
          </Space>
        </Space>
        <Space wrap>
          <Button size="small" icon={<FolderOpenOutlined />} onClick={() => onViewChange("projects")}>
            Projects
          </Button>
          <Button size="small" icon={<PlayCircleOutlined />} onClick={() => onViewChange("audit-runs")}>
            Audit
          </Button>
          <Button size="small" icon={<BugOutlined />} onClick={() => onViewChange("findings")}>
            Findings
          </Button>
          <Button size="small" icon={<BugOutlined />} onClick={() => onViewChange("finding-review")}>
            Review
          </Button>
          <Button size="small" icon={<FileTextOutlined />} onClick={() => onViewChange("reports")}>
            Reports
          </Button>
        </Space>
      </Flex>
    </section>
  );
}

import {
  FileTextOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { Alert, Button, Card, Collapse, Descriptions, List, Space, Statistic, Tag, Typography } from "antd";
import type { AuditRun, PipelineStatus, Project } from "../types";
import { isActiveRun } from "../utils/format";
import { PageHeader } from "../components/PageHeader";

const { Text } = Typography;

type Props = {
  agentRunsCount: number;
  auditRun?: AuditRun;
  lastResponse?: unknown;
  loading: boolean;
  pipelineStatus?: PipelineStatus;
  reportsCount: number;
  selectedProject?: Project;
  onCancelAuditRun: () => void;
  onGenerateReport: () => void;
  onRunJudge: () => void;
  onRunPipeline: () => void;
  onRunSca: () => void;
  onStartAudit: () => void;
};

export function AuditRunsPage({
  agentRunsCount,
  auditRun,
  lastResponse,
  loading,
  pipelineStatus,
  reportsCount,
  selectedProject,
  onCancelAuditRun,
  onGenerateReport,
  onRunJudge,
  onRunPipeline,
  onRunSca,
  onStartAudit,
}: Props) {
  const pageActions = (
    <div className="action-bar">
      <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} disabled={!selectedProject} onClick={onStartAudit}>启动审计</Button>
      <Button icon={<PlayCircleOutlined />} loading={loading} disabled={!auditRun} onClick={onRunPipeline}>一键闭环</Button>
      <Button icon={<SafetyCertificateOutlined />} loading={loading} disabled={!auditRun} onClick={onRunSca}>SCA 扫描</Button>
      <Button icon={<SafetyCertificateOutlined />} loading={loading} disabled={!auditRun} onClick={onRunJudge}>研判</Button>
      <Button icon={<FileTextOutlined />} loading={loading} disabled={!auditRun} onClick={onGenerateReport}>报告</Button>
      <Button
        danger
        icon={<StopOutlined />}
        loading={loading}
        disabled={!auditRun || !isActiveRun(auditRun.status, pipelineStatus?.current?.status)}
        onClick={onCancelAuditRun}
      >
        取消
      </Button>
    </div>
  );

  return (
    <>
      <PageHeader title="Audit Runs" actions={pageActions} />
      {!selectedProject && (
        <Alert
          className="section"
          type="warning"
          showIcon
          message="未选择项目"
          description="请先在 Projects 页面导入并选择一个项目。"
        />
      )}

      <div className="run-summary-grid section">
        <Card>
          <Statistic title="Project" value={selectedProject?.name || "-"} />
          <Text type="secondary">{selectedProject?.project_id || "No project selected"}</Text>
        </Card>
        <Card>
          <Statistic title="AuditRun" value={auditRun?.audit_run_id || "-"} />
          <Text type="secondary">{auditRun?.status || "No run created"}</Text>
        </Card>
        <Card>
          <Statistic title="Pipeline" value={pipelineStatus?.current?.stage || "-"} />
          <Tag color={pipelineStatus?.current?.status === "failed" ? "red" : pipelineStatus?.current?.status === "completed" ? "green" : "blue"}>
            {pipelineStatus?.current?.status || "-"}
          </Tag>
        </Card>
        <Card>
          <Statistic title="Reports" value={reportsCount} />
          <Text type="secondary">AgentRuns {agentRunsCount}</Text>
        </Card>
      </div>

      {pipelineStatus?.current?.error && <Alert className="section" type="error" showIcon message={pipelineStatus.current.error} />}
      {pipelineStatus?.runtime_control?.cancel_requested && (
        <Alert
          className="section"
          type="warning"
          showIcon
          message="取消已请求"
          description={`${pipelineStatus.runtime_control.cancel_reason || "cancel_requested"} ${pipelineStatus.runtime_control.cancel_requested_at || ""}`}
        />
      )}

      <div className="content-grid section">
        <Card title="Run Context">
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="Project">{selectedProject?.name || "-"}</Descriptions.Item>
            <Descriptions.Item label="Project ID">{selectedProject?.project_id || "-"}</Descriptions.Item>
            <Descriptions.Item label="AuditRun ID">{auditRun?.audit_run_id || "-"}</Descriptions.Item>
            <Descriptions.Item label="AuditRun Status">{auditRun?.status || "-"}</Descriptions.Item>
            <Descriptions.Item label="Created At">{auditRun?.created_at || "-"}</Descriptions.Item>
          </Descriptions>
          {Boolean(lastResponse) && (
            <Collapse
              className="table-toolbar"
              size="small"
              items={[
                {
                  key: "last-response",
                  label: "Last Response",
                  children: <pre>{JSON.stringify(lastResponse, null, 2)}</pre>,
                },
              ]}
            />
          )}
        </Card>
        <Card title="Pipeline State">
          <Space direction="vertical" size={16} className="drawer-stack">
            <Space wrap>
              {Object.entries(pipelineStatus?.counts?.findings || {}).map(([status, count]) => (
                <Tag key={status}>{status}: {count}</Tag>
              ))}
              {Object.entries(pipelineStatus?.counts?.validation_attempts || {}).map(([status, count]) => (
                <Tag key={`attempt-${status}`}>attempt {status}: {count}</Tag>
              ))}
              <Tag>reports: {pipelineStatus?.counts?.reports ?? 0}</Tag>
            </Space>
            <List
              dataSource={pipelineStatus?.events || []}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={<Space><Tag>{item.event_type}</Tag><Text>{item.created_at}</Text></Space>}
                    description={<pre>{JSON.stringify(item.payload || {}, null, 2)}</pre>}
                  />
                </List.Item>
              )}
            />
          </Space>
        </Card>
      </div>
    </>
  );
}

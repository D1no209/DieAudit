import { FileTextOutlined, PlayCircleOutlined, SafetyCertificateOutlined, StopOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Form, Input, List, Space, Table, Tabs, Tag, Typography, Upload } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { FormInstance } from "antd/es/form";
import type { UploadFile } from "antd/es/upload/interface";
import type { AgentRun, ArtifactRef, AuditRun, PipelineStatus, Project, ReportArtifact } from "../types";
import { isActiveRun } from "../utils/format";

const { Paragraph, Text } = Typography;

type Props = {
  agentColumns: ColumnsType<AgentRun>;
  agentRuns: AgentRun[];
  auditRun?: AuditRun;
  gitForm: FormInstance;
  lastResponse?: any;
  loading: boolean;
  pipelineStatus?: PipelineStatus;
  projectColumns: ColumnsType<Project>;
  projects: Project[];
  reports: ReportArtifact[];
  selectedProject?: Project;
  selectedProjectId?: string;
  zipFiles: UploadFile[];
  zipForm: FormInstance;
  onCreateGitProject: (values: { name: string; git_url: string; ref?: string }) => void;
  onGenerateReport: () => void;
  onOpenArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onRunJudge: () => void;
  onRunPipeline: () => void;
  onRunSca: () => void;
  onSelectProject: (projectId: string) => void;
  onSetZipFiles: (files: UploadFile[]) => void;
  onStartAudit: () => void;
  onCancelAuditRun: () => void;
  onUploadZipProject: (values: { name: string }) => void;
};

export function ProjectsPage({
  agentColumns,
  agentRuns,
  auditRun,
  gitForm,
  lastResponse,
  loading,
  pipelineStatus,
  projectColumns,
  projects,
  reports,
  selectedProject,
  selectedProjectId,
  zipFiles,
  zipForm,
  onCancelAuditRun,
  onCreateGitProject,
  onGenerateReport,
  onOpenArtifact,
  onRunJudge,
  onRunPipeline,
  onRunSca,
  onSelectProject,
  onSetZipFiles,
  onStartAudit,
  onUploadZipProject,
}: Props) {
  return (
    <>
      <div className="action-bar section">
        <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={onStartAudit}>启动审计</Button>
        <Button icon={<PlayCircleOutlined />} loading={loading} onClick={onRunPipeline}>一键闭环</Button>
        <Button icon={<SafetyCertificateOutlined />} loading={loading} onClick={onRunSca}>SCA 扫描</Button>
        <Button icon={<SafetyCertificateOutlined />} loading={loading} onClick={onRunJudge}>研判</Button>
        <Button icon={<FileTextOutlined />} loading={loading} onClick={onGenerateReport}>报告</Button>
        <Button danger icon={<StopOutlined />} loading={loading} disabled={!auditRun || !isActiveRun(auditRun.status, pipelineStatus?.current?.status)} onClick={onCancelAuditRun}>取消</Button>
      </div>

      <div className="workspace-grid section">
        <Card title="Projects">
          <Tabs
            items={[
              {
                key: "git",
                label: "Git",
                children: (
                  <Form form={gitForm} layout="vertical" onFinish={onCreateGitProject}>
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                    <Form.Item name="git_url" label="Git URL" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                    <Form.Item name="ref" label="Ref">
                      <Input />
                    </Form.Item>
                    <Button htmlType="submit" type="primary" loading={loading}>导入 Git</Button>
                  </Form>
                ),
              },
              {
                key: "zip",
                label: "Zip",
                children: (
                  <Form form={zipForm} layout="vertical" onFinish={onUploadZipProject}>
                    <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                    <Upload beforeUpload={() => false} maxCount={1} fileList={zipFiles} onChange={({ fileList }) => onSetZipFiles(fileList)}>
                      <Button>选择 zip</Button>
                    </Upload>
                    <Button className="form-action" htmlType="submit" type="primary" loading={loading}>上传 Zip</Button>
                  </Form>
                ),
              },
            ]}
          />
          <Table
            rowKey="project_id"
            size="small"
            columns={projectColumns}
            dataSource={projects}
            pagination={false}
            rowSelection={{ type: "radio", selectedRowKeys: selectedProjectId ? [selectedProjectId] : [], onChange: ([key]) => onSelectProject(String(key)) }}
          />
        </Card>
        <Card title="Current AuditRun">
          <Paragraph>
            <Text strong>Project: </Text>{selectedProject?.name || "-"}
          </Paragraph>
          <Paragraph>
            <Text strong>AuditRun: </Text>{auditRun?.audit_run_id || "-"}
          </Paragraph>
          <Paragraph>
            <Text strong>Status: </Text>{auditRun?.status || "-"}
          </Paragraph>
          <Paragraph>
            <Text strong>Pipeline: </Text>
            <Tag color={pipelineStatus?.current?.status === "failed" ? "red" : pipelineStatus?.current?.status === "completed" ? "green" : "blue"}>
              {pipelineStatus?.current?.stage || "-"} / {pipelineStatus?.current?.status || "-"}
            </Tag>
          </Paragraph>
          {pipelineStatus?.current?.error && <Alert type="error" showIcon message={pipelineStatus.current.error} />}
          {pipelineStatus?.runtime_control?.cancel_requested && (
            <Alert
              type="warning"
              showIcon
              message="取消已请求"
              description={`${pipelineStatus.runtime_control.cancel_reason || "cancel_requested"} ${pipelineStatus.runtime_control.cancel_requested_at || ""}`}
            />
          )}
          <pre>{JSON.stringify(lastResponse || { hint: "Import a project, start an audit, then run SCA." }, null, 2)}</pre>
        </Card>
      </div>

      <Tabs
        className="section"
        items={[
          { key: "agents", label: "AgentRuns", children: <Card><Table rowKey="agent_run_id" columns={agentColumns} dataSource={agentRuns} pagination={false} /></Card> },
          {
            key: "pipeline",
            label: "Pipeline",
            children: (
              <Card>
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
            ),
          },
          {
            key: "reports",
            label: "Reports",
            children: (
              <Card>
                <List
                  dataSource={reports}
                  renderItem={(item) => (
                    <List.Item>
                      <List.Item.Meta title={item.kind} description={item.artifact?.relative_path || item.path} />
                      <Space>
                        <Tag>{String(item.summary?.finding_count ?? 0)} findings</Tag>
                        <Button size="small" icon={<FileTextOutlined />} onClick={() => onOpenArtifact(item.artifact, item.path)}>下载</Button>
                      </Space>
                    </List.Item>
                  )}
                />
              </Card>
            ),
          },
        ]}
      />
    </>
  );
}

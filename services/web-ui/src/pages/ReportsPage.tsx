import { FileTextOutlined } from "@ant-design/icons";
import { Alert, Button, Card, List, Space, Tag, Typography } from "antd";
import type { ArtifactRef, AuditRun, ReportArtifact } from "../types";
import { PageHeader } from "../components/PageHeader";

const { Text } = Typography;

type Props = {
  auditRun?: AuditRun;
  loading: boolean;
  reports: ReportArtifact[];
  onGenerateReport: () => void;
  onOpenArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
};

export function ReportsPage({ auditRun, loading, reports, onGenerateReport, onOpenArtifact }: Props) {
  const pageActions = (
    <div className="action-bar">
      <Button icon={<FileTextOutlined />} loading={loading} disabled={!auditRun} onClick={onGenerateReport}>生成报告</Button>
    </div>
  );

  return (
    <>
      <PageHeader title="Reports" actions={pageActions} />
      {!auditRun && (
        <Alert
          className="section"
          type="info"
          showIcon
          message="No active AuditRun"
          description="Create or select an audit run before generating reports."
        />
      )}
      <Card
        className="section"
        title="Report Artifacts"
        extra={<Text type="secondary">{auditRun?.audit_run_id || "No run"}</Text>}
      >
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
    </>
  );
}

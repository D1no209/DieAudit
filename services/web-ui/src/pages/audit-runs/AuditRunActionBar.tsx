import {
  FileTextOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { Button } from "antd";
import type { AuditRun, PipelineStatus, Project } from "../../types";
import { isActiveRun } from "../../utils/format";

type Props = {
  auditRun?: AuditRun;
  loading: boolean;
  pipelineStatus?: PipelineStatus;
  selectedProject?: Project;
  onCancelAuditRun: () => void;
  onGenerateReport: () => void;
  onRunJudge: () => void;
  onRunPipeline: () => void;
  onRunSca: () => void;
  onStartAudit: () => void;
};

export function AuditRunActionBar({
  auditRun,
  loading,
  pipelineStatus,
  selectedProject,
  onCancelAuditRun,
  onGenerateReport,
  onRunJudge,
  onRunPipeline,
  onRunSca,
  onStartAudit,
}: Props) {
  return (
    <div className="action-bar">
      <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} disabled={!selectedProject} onClick={onStartAudit}>
        启动审计
      </Button>
      <Button icon={<PlayCircleOutlined />} loading={loading} disabled={!auditRun} onClick={onRunPipeline}>
        一键闭环
      </Button>
      <Button icon={<SafetyCertificateOutlined />} loading={loading} disabled={!auditRun} onClick={onRunSca}>
        SCA 扫描
      </Button>
      <Button icon={<SafetyCertificateOutlined />} loading={loading} disabled={!auditRun} onClick={onRunJudge}>
        研判
      </Button>
      <Button icon={<FileTextOutlined />} loading={loading} disabled={!auditRun} onClick={onGenerateReport}>
        报告
      </Button>
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
}

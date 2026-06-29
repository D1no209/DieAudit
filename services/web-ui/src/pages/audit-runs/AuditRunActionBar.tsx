import { Code, FileText, PlayCircle, ShieldCheck, Square } from "lucide-react";
import type { AuditRun, PipelineStatus, Project } from "../../types";
import { Button } from "../../ui";
import { isActiveRun } from "../../utils/format";

type Props = {
  auditRun?: AuditRun;
  loading: boolean;
  pipelineStatus?: PipelineStatus;
  selectedProject?: Project;
  onCancelAuditRun: () => void;
  onGenerateReport: () => void;
  onRunJudge: () => void;
  onRunCodeAnalysis: () => void;
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
  onRunCodeAnalysis,
  onRunPipeline,
  onRunSca,
  onStartAudit,
}: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="primary" icon={<PlayCircle className="h-4 w-4" />} loading={loading} disabled={!selectedProject} onClick={onStartAudit}>启动审计</Button>
      <Button icon={<PlayCircle className="h-4 w-4" />} loading={loading} disabled={!auditRun} onClick={onRunPipeline}>一键闭环</Button>
      <Button icon={<ShieldCheck className="h-4 w-4" />} loading={loading} disabled={!auditRun} onClick={onRunSca}>SCA 扫描</Button>
      <Button icon={<Code className="h-4 w-4" />} loading={loading} disabled={!auditRun} onClick={onRunCodeAnalysis}>代码批量分析</Button>
      <Button icon={<ShieldCheck className="h-4 w-4" />} loading={loading} disabled={!auditRun} onClick={onRunJudge}>研判</Button>
      <Button icon={<FileText className="h-4 w-4" />} loading={loading} disabled={!auditRun} onClick={onGenerateReport}>报告</Button>
      <Button
        variant="danger"
        icon={<Square className="h-4 w-4" />}
        loading={loading}
        disabled={!auditRun || !isActiveRun(auditRun.status, pipelineStatus?.current?.status)}
        onClick={onCancelAuditRun}
      >
        取消
      </Button>
    </div>
  );
}

import { Alert } from "antd";
import type { AuditRun, PipelineStatus, Project } from "../types";
import { PageHeader } from "../components/PageHeader";
import { AuditRunActionBar } from "./audit-runs/AuditRunActionBar";
import { AuditRunSummary } from "./audit-runs/AuditRunSummary";
import { PipelineStatePanel } from "./audit-runs/PipelineStatePanel";
import { RunContextPanel } from "./audit-runs/RunContextPanel";

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
    <AuditRunActionBar
      auditRun={auditRun}
      loading={loading}
      pipelineStatus={pipelineStatus}
      selectedProject={selectedProject}
      onCancelAuditRun={onCancelAuditRun}
      onGenerateReport={onGenerateReport}
      onRunJudge={onRunJudge}
      onRunPipeline={onRunPipeline}
      onRunSca={onRunSca}
      onStartAudit={onStartAudit}
    />
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

      <AuditRunSummary
        agentRunsCount={agentRunsCount}
        auditRun={auditRun}
        pipelineStatus={pipelineStatus}
        reportsCount={reportsCount}
        selectedProject={selectedProject}
      />

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
        <RunContextPanel auditRun={auditRun} lastResponse={lastResponse} selectedProject={selectedProject} />
        <PipelineStatePanel pipelineStatus={pipelineStatus} />
      </div>
    </>
  );
}

import { useState } from "react";
import type { AgentRuntimeAdapter, AuditRun, CodeAnalysisTask, CreateAuditRunPayload, PipelineStatus, Project } from "../types";
import { PageHeader } from "../components/PageHeader";
import { Alert } from "../ui";
import { AuditRunActionBar } from "./audit-runs/AuditRunActionBar";
import { AuditRunConfigModal } from "./audit-runs/AuditRunConfigModal";
import { AuditRunSummary } from "./audit-runs/AuditRunSummary";
import { CodeAnalysisTasksPanel } from "./audit-runs/CodeAnalysisTasksPanel";
import { PipelineStatePanel } from "./audit-runs/PipelineStatePanel";
import { RunContextPanel } from "./audit-runs/RunContextPanel";

type Props = {
  agentRunsCount: number;
  agentRuntimes: AgentRuntimeAdapter[];
  auditRun?: AuditRun;
  codeAnalysisTasks: CodeAnalysisTask[];
  lastResponse?: unknown;
  loading: boolean;
  pipelineStatus?: PipelineStatus;
  reportsCount: number;
  selectedProject?: Project;
  onCancelAuditRun: () => void;
  onGenerateReport: () => void;
  onRunCodeAnalysis: () => void;
  onRunJudge: () => void;
  onRunPipeline: () => void;
  onRunSca: () => void;
  onStartAudit: (values: CreateAuditRunPayload) => void;
};

export function AuditRunsPage({
  agentRunsCount,
  agentRuntimes,
  auditRun,
  codeAnalysisTasks,
  lastResponse,
  loading,
  pipelineStatus,
  reportsCount,
  selectedProject,
  onCancelAuditRun,
  onGenerateReport,
  onRunCodeAnalysis,
  onRunJudge,
  onRunPipeline,
  onRunSca,
  onStartAudit,
}: Props) {
  const [configOpen, setConfigOpen] = useState(false);

  function submitAuditConfig(values: CreateAuditRunPayload) {
    onStartAudit(values);
    setConfigOpen(false);
  }

  const pageActions = (
    <AuditRunActionBar
      auditRun={auditRun}
      loading={loading}
      pipelineStatus={pipelineStatus}
      selectedProject={selectedProject}
      onCancelAuditRun={onCancelAuditRun}
      onGenerateReport={onGenerateReport}
      onRunCodeAnalysis={onRunCodeAnalysis}
      onRunJudge={onRunJudge}
      onRunPipeline={onRunPipeline}
      onRunSca={onRunSca}
      onStartAudit={() => setConfigOpen(true)}
    />
  );

  return (
    <>
      <PageHeader title="Audit Runs" actions={pageActions} />
      {!selectedProject && (
        <Alert
          className="mb-5"
          tone="warning"
          title="未选择项目"
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

      {pipelineStatus?.current?.error && <Alert className="mb-5" tone="danger" title={pipelineStatus.current.error} />}
      {pipelineStatus?.runtime_control?.cancel_requested && (
        <Alert
          className="mb-5"
          tone="warning"
          title="取消已请求"
          description={`${pipelineStatus.runtime_control.cancel_reason || "cancel_requested"} ${pipelineStatus.runtime_control.cancel_requested_at || ""}`}
        />
      )}

      <div className="mb-5 grid gap-4 xl:grid-cols-[minmax(360px,0.9fr)_minmax(480px,1.1fr)]">
        <RunContextPanel auditRun={auditRun} lastResponse={lastResponse} selectedProject={selectedProject} />
        <PipelineStatePanel pipelineStatus={pipelineStatus} />
      </div>
      <CodeAnalysisTasksPanel tasks={codeAnalysisTasks} />
      <AuditRunConfigModal
        agentRuntimes={agentRuntimes}
        loading={loading}
        open={configOpen}
        onCancel={() => setConfigOpen(false)}
        onSubmit={submitAuditConfig}
      />
    </>
  );
}

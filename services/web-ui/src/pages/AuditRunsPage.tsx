import { useState } from "react";
import type { AgentRuntimeAdapter, AuditRun, CodeAnalysisTask, CreateAuditRunPayload, PipelineStatus, Project } from "../types";
import { PageHeader } from "../components/PageHeader";
import { Alert, Badge, Panel } from "../ui";
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
      <PageHeader title="Audit Runs" eyebrow="Run control" actions={pageActions} />
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

      <div className="mb-5 grid gap-4 xl:grid-cols-[minmax(280px,0.68fr)_minmax(560px,1.45fr)_minmax(300px,0.72fr)]">
        <RunContextPanel auditRun={auditRun} lastResponse={lastResponse} selectedProject={selectedProject} />
        <PipelineStatePanel pipelineStatus={pipelineStatus} />
        <Panel title="Action Queue" dense>
          <div className="grid gap-3 text-sm">
            <div className="grid grid-cols-2 gap-2">
              <StatusTile label="run" value={auditRun?.status || "no-run"} />
              <StatusTile label="stage" value={pipelineStatus?.current?.status || "idle"} />
              <StatusTile label="reports" value={String(reportsCount)} />
              <StatusTile label="agents" value={String(agentRunsCount)} />
            </div>
            {nextActionText({ auditRun, pipelineStatus, selectedProject })}
            {warningEvents(pipelineStatus).slice(0, 3).map((item) => (
              <div key={item.id} className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950">
                <div className="flex items-center justify-between gap-2">
                  <div className="truncate font-semibold">{item.event_type}</div>
                  <Badge tone="warning">warning</Badge>
                </div>
                <div className="mt-1 line-clamp-2 text-xs">{eventProblemText(item.payload)}</div>
              </div>
            ))}
            {!warningEvents(pipelineStatus).length ? <Alert tone="success" title="No current warnings" description="Failures and warning events will collect here while the run executes." /> : null}
          </div>
        </Panel>
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

function StatusTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-slate-300 bg-slate-50 px-2.5 py-2">
      <div className="text-[10px] font-semibold uppercase text-slate-500">{label}</div>
      <div className="mt-1 truncate text-sm font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function warningEvents(pipelineStatus?: PipelineStatus) {
  return (pipelineStatus?.events || []).filter((item) => /warning|failed|unavailable|skipped|completed_with_warnings/i.test(item.event_type));
}

function nextActionText({
  auditRun,
  pipelineStatus,
  selectedProject,
}: {
  auditRun?: AuditRun;
  pipelineStatus?: PipelineStatus;
  selectedProject?: Project;
}) {
  if (!selectedProject) {
    return <p className="leading-6 text-slate-600">先在 Projects 选择或导入项目，然后创建 AuditRun。</p>;
  }
  if (!auditRun) {
    return <p className="leading-6 text-slate-600">点击启动审计，选择预设后创建第一条 AuditRun。</p>;
  }
  if (pipelineStatus?.runtime_control?.cancel_requested) {
    return <p className="leading-6 text-amber-800">取消请求已提交，等待当前运行阶段结束并清理 runtime。</p>;
  }
  if (pipelineStatus?.current?.status === "failed" || auditRun.status === "failed") {
    return <p className="leading-6 text-red-700">查看失败事件和容器日志；需要保留现场时重新创建任务并启用失败保留。</p>;
  }
  if (auditRun.status === "created" || auditRun.status === "pending") {
    return <p className="leading-6 text-slate-600">点击一键闭环，按标准 pipeline 执行审计。</p>;
  }
  if (auditRun.status === "completed" || auditRun.status === "completed_with_warnings") {
    return <p className="leading-6 text-slate-600">审计已结束，继续查看 Findings、Agent Runs、Whiteboard 和 Reports。</p>;
  }
  return <p className="leading-6 text-slate-600">当前阶段正在运行，优先观察 Pipeline State 和 Agent Runs 图谱。</p>;
}

function eventProblemText(payload: Record<string, unknown>) {
  for (const key of ["error", "reason", "step", "stage", "status"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "See raw pipeline event for details.";
}

import type { AuditRunEvent, PipelineStatus } from "../../types";
import { Alert, Badge, EmptyState, Panel } from "../../ui";
import { cn } from "../../ui/utils";
import { statusTone } from "../../utils/format";

type Props = {
  pipelineStatus?: PipelineStatus;
};

export function PipelineStatePanel({ pipelineStatus }: Props) {
  const warningEvents = (pipelineStatus?.events || []).filter((item) =>
    /warning|failed|unavailable|skipped|completed_with_warnings/i.test(item.event_type),
  );
  const stageStatuses = inferStageStatuses(pipelineStatus);

  return (
    <Panel title="Pipeline State">
      <div className="grid gap-4">
        {pipelineStatus?.current?.status === "completed_with_warnings" ? <Alert tone="warning" title="Pipeline completed with warnings" /> : null}
        {warningEvents.length > 0 ? (
          <Alert
            tone="warning"
            title={`${warningEvents.length} warning or failure event(s) recorded`}
            description={warningEvents.slice(0, 3).map((item) => item.event_type).join(", ")}
          />
        ) : null}
        <div className="flex flex-wrap gap-2">
          {Object.entries(pipelineStatus?.counts?.findings || {}).map(([status, count]) => (
            <Badge key={status}>{status}: {count}</Badge>
          ))}
          {Object.entries(pipelineStatus?.counts?.validation_attempts || {}).map(([status, count]) => (
            <Badge key={`attempt-${status}`}>attempt {status}: {count}</Badge>
          ))}
          <Badge>reports: {pipelineStatus?.counts?.reports ?? 0}</Badge>
        </div>
        <div className="grid gap-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-slate-900">Standard pipeline</div>
            <Badge>{pipelineStatus?.current?.stage || "idle"}</Badge>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {standardStages.map((stage, index) => {
              const status = stageStatuses[stage.key] || "pending";
              return (
                <div key={stage.key} className={cn("flex items-center gap-3 rounded-lg border px-3 py-2", stageToneClass(status))}>
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border bg-white text-xs font-semibold">
                    {index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-slate-900">{stage.label}</div>
                    <div className="truncate text-xs text-slate-500">{stage.key}</div>
                  </div>
                  <Badge tone={statusTone(status)}>{status}</Badge>
                </div>
              );
            })}
          </div>
        </div>
        {(pipelineStatus?.events || []).length ? (
          <div className="grid gap-3">
            {(pipelineStatus?.events || []).map((item) => (
              <div key={item.id} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge>{item.event_type}</Badge>
                  <span className="text-xs text-slate-500">{item.created_at}</span>
                </div>
                <p className="mb-2 text-sm text-slate-700">{eventSummary(item)}</p>
                <details className="group">
                  <summary className="cursor-pointer text-xs font-medium text-slate-500 group-open:mb-2">
                    Raw event payload
                  </summary>
                  <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded border border-slate-200 bg-white p-3 text-xs">
                    {JSON.stringify(item.payload || {}, null, 2)}
                  </pre>
                </details>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState description="No pipeline events yet" />
        )}
      </div>
    </Panel>
  );
}

const standardStages = [
  { key: "snapshot-ready", label: "Snapshot" },
  { key: "structure-discovery", label: "Structure Discovery" },
  { key: "agent-audit", label: "Agent Audit" },
  { key: "code-analysis", label: "Code Analysis" },
  { key: "value-triage", label: "Value Triage" },
  { key: "whiteboard-swarm", label: "Whiteboard Swarm" },
  { key: "validation-judgement", label: "Validation Judgement" },
  { key: "feedback-loop", label: "Feedback Loop" },
  { key: "poc-writing", label: "PoC Writing" },
  { key: "poc-verification", label: "PoC Verification" },
  { key: "report", label: "Report" },
  { key: "runtime-cleanup", label: "Runtime Cleanup" },
] as const;

function inferStageStatuses(pipelineStatus?: PipelineStatus) {
  const statuses: Record<string, string> = {};
  for (const item of pipelineStatus?.events || []) {
    const payload = item.payload || {};
    const stage = valueText(payload.stage) || valueText(payload.step);
    if (!stage) continue;
    if (/started$/i.test(item.event_type)) statuses[stage] = "running";
    if (/completed$/i.test(item.event_type)) statuses[stage] = valueText(payload.status) || "completed";
    if (/failed$/i.test(item.event_type)) statuses[stage] = "failed";
    if (/skipped$/i.test(item.event_type)) statuses[stage] = "skipped";
  }
  const current = pipelineStatus?.current;
  if (current?.stage && current.status) {
    statuses[current.stage] = current.status;
  }
  return statuses;
}

function stageToneClass(status: string) {
  if (["completed", "succeeded"].includes(status)) return "border-emerald-200 bg-emerald-50";
  if (status === "running") return "border-blue-200 bg-blue-50";
  if (status === "failed") return "border-red-200 bg-red-50";
  if (status === "skipped") return "border-amber-200 bg-amber-50";
  return "border-slate-200 bg-slate-50";
}

function eventSummary(item: AuditRunEvent) {
  const payload = item.payload || {};
  const values = [
    valueText(payload.step),
    valueText(payload.status),
    valueText(payload.terminal_status),
    valueText(payload.error),
    reportText(payload.report),
    resultText(payload.result),
  ].filter(Boolean);
  return values.length ? values.join(" / ") : "Event recorded";
}

function valueText(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function reportText(value: unknown) {
  if (!isRecord(value)) {
    return "";
  }
  const reportId = valueText(value.report_id);
  const summary = isRecord(value.summary) ? value.summary : {};
  const findingCount = typeof summary.finding_count === "number" ? summary.finding_count : undefined;
  return ["report", reportId, findingCount === undefined ? "" : `${findingCount} findings`].filter(Boolean).join(" ");
}

function resultText(value: unknown) {
  if (!isRecord(value)) {
    return "";
  }
  const parts = [
    value.ok === false ? "not ok" : "",
    valueText(value.reason),
    valueText(value.error),
    typeof value.count === "number" ? `${value.count} item(s)` : "",
    typeof value.finding_count === "number" ? `${value.finding_count} finding(s)` : "",
  ].filter(Boolean);
  return parts.join(" / ");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

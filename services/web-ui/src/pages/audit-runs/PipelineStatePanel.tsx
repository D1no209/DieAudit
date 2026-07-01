import type { AuditRunEvent, PipelineStatus } from "../../types";
import { STANDARD_PIPELINE_STAGES } from "../../displayMeta";
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
    <Panel title="Pipeline State" dense>
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
        <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
          <div className="grid gap-1.5">
            <div className="mb-1 flex items-center justify-between gap-2">
              <div className="text-sm font-semibold text-slate-900">Stage rail</div>
              <Badge>{pipelineStatus?.current?.stage || "idle"}</Badge>
            </div>
            {STANDARD_PIPELINE_STAGES.map((stage, index) => {
              const status = stageStatuses[stage.key] || "pending";
              return (
                <div key={stage.key} className={cn("grid grid-cols-[26px_minmax(0,1fr)_auto] items-center gap-2 rounded-lg border px-2.5 py-2", stageToneClass(status))}>
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border bg-white text-xs font-semibold">
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
          <div className="grid gap-3">
            <StageDetail pipelineStatus={pipelineStatus} stageStatuses={stageStatuses} />
            <EventFeed events={pipelineStatus?.events || []} />
          </div>
        </div>
      </div>
    </Panel>
  );
}

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
  if (["completed", "succeeded"].includes(status)) return "border-emerald-300 bg-emerald-50";
  if (status === "running") return "border-cyan-300 bg-cyan-50";
  if (status === "failed") return "border-red-300 bg-red-50";
  if (status === "skipped") return "border-amber-300 bg-amber-50";
  return "border-slate-300 bg-slate-50";
}

function StageDetail({
  pipelineStatus,
  stageStatuses,
}: {
  pipelineStatus?: PipelineStatus;
  stageStatuses: Record<string, string>;
}) {
  const currentKey = pipelineStatus?.current?.stage || STANDARD_PIPELINE_STAGES.find((stage) => stageStatuses[stage.key] === "running")?.key;
  const currentStage = STANDARD_PIPELINE_STAGES.find((stage) => stage.key === currentKey) || STANDARD_PIPELINE_STAGES[0];
  const status = currentKey ? stageStatuses[currentKey] || pipelineStatus?.current?.status || "pending" : "pending";
  return (
    <div className="rounded-lg border border-slate-300 bg-white p-3">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2">
          <span className="rounded-md border border-cyan-300 bg-cyan-50 p-1.5 text-cyan-900">{currentStage.icon}</span>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-950">{currentStage.label}</div>
            <p className="mt-1 text-xs leading-5 text-slate-600">{currentStage.description}</p>
          </div>
        </div>
        <Badge tone={statusTone(status)}>{status}</Badge>
      </div>
      <dl className="grid gap-2 text-xs sm:grid-cols-2">
        <Info label="stage" value={currentStage.key} />
        <Info label="failure policy" value={currentStage.key === "runtime-cleanup" ? "ALWAYS_RUN" : currentStage.key === "whiteboard-swarm" || currentStage.key === "feedback-loop" ? "CONTINUE_WITH_WARNING" : "FAIL_FAST"} />
        <Info label="findings" value={String(Object.values(pipelineStatus?.counts?.findings || {}).reduce((total, count) => total + count, 0))} />
        <Info label="reports" value={String(pipelineStatus?.counts?.reports ?? 0)} />
      </dl>
    </div>
  );
}

function EventFeed({ events }: { events: AuditRunEvent[] }) {
  if (!events.length) return <EmptyState description="No pipeline events yet" />;
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-semibold text-slate-900">Event feed</div>
        <Badge>{events.length} events</Badge>
      </div>
      {events.slice(0, 8).map((item) => (
        <div key={item.id} className="rounded-lg border border-slate-300 bg-slate-50 p-3">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone={eventTone(item.event_type)}>{item.event_type}</Badge>
            <span className="text-xs text-slate-500">{item.created_at}</span>
          </div>
          <p className="mb-2 text-sm text-slate-700">{eventSummary(item)}</p>
          <details className="group">
            <summary className="cursor-pointer text-xs font-semibold text-slate-500 group-open:mb-2">
              Raw event payload
            </summary>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded border border-slate-300 bg-white p-3 text-xs text-slate-800">
              {JSON.stringify(item.payload || {}, null, 2)}
            </pre>
          </details>
        </div>
      ))}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded border border-slate-200 bg-slate-50 px-2 py-1.5">
      <dt className="font-semibold uppercase text-slate-500">{label}</dt>
      <dd className="mt-0.5 truncate text-slate-800">{value}</dd>
    </div>
  );
}

function eventTone(eventType: string) {
  if (/failed|error/i.test(eventType)) return "danger";
  if (/warning|skipped|unavailable/i.test(eventType)) return "warning";
  if (/completed/i.test(eventType)) return "success";
  if (/started|queued|running/i.test(eventType)) return "processing";
  return "neutral";
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

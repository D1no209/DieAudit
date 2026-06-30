import type { AuditRunEvent, PipelineStatus } from "../../types";
import { Alert, Badge, EmptyState, Panel } from "../../ui";

type Props = {
  pipelineStatus?: PipelineStatus;
};

export function PipelineStatePanel({ pipelineStatus }: Props) {
  const warningEvents = (pipelineStatus?.events || []).filter((item) =>
    /warning|failed|unavailable|skipped|completed_with_warnings/i.test(item.event_type),
  );

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

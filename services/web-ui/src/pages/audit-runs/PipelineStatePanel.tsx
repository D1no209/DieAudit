import type { PipelineStatus } from "../../types";
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
                <pre>{JSON.stringify(item.payload || {}, null, 2)}</pre>
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

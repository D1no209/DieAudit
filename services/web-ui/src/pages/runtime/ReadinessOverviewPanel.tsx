import type { RuntimeReadiness } from "../../types";
import { Alert, Badge, MetricCard, Panel } from "../../ui";

type Props = {
  runtimeReadiness?: RuntimeReadiness;
};

export function ReadinessOverviewPanel({ runtimeReadiness }: Props) {
  if (!runtimeReadiness) {
    return (
      <Panel title="Production Readiness">
        <Alert tone="warning" title="Readiness data is unavailable." />
      </Panel>
    );
  }

  return (
    <Panel title="Production Readiness">
      <div className="grid gap-3 md:grid-cols-4">
        <MetricCard label="Status" value={runtimeReadiness.ok ? "Ready" : "Not Ready"} />
        <MetricCard label="Blocking" value={runtimeReadiness.summary?.fail ?? 0} />
        <MetricCard label="Warnings" value={runtimeReadiness.summary?.warn ?? 0} />
        <MetricCard label="Passing" value={runtimeReadiness.summary?.pass ?? 0} />
      </div>
      {runtimeReadiness.blocking_checks?.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {runtimeReadiness.blocking_checks.slice(0, 4).map((item) => (
            <Badge key={item.id} tone="danger">{item.title}</Badge>
          ))}
        </div>
      ) : null}
      {!runtimeReadiness.ok ? (
        <p className="mt-3 text-sm text-slate-500">Resolve blocking checks before exposing the platform beyond a trusted local deployment.</p>
      ) : null}
    </Panel>
  );
}

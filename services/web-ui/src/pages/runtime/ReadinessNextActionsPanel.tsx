import type { RuntimeReadiness } from "../../types";
import { Alert, Panel } from "../../ui";

type Props = {
  runtimeReadiness?: RuntimeReadiness;
};

export function ReadinessNextActionsPanel({ runtimeReadiness }: Props) {
  const actions = runtimeReadiness?.next_actions || [];

  if (!runtimeReadiness) {
    return (
      <Panel title="Next Actions">
        <Alert tone="warning" title="Readiness data is unavailable." />
      </Panel>
    );
  }

  if (actions.length === 0) {
    return (
      <Panel title="Next Actions">
        <Alert tone="success" title="No production readiness actions are currently required." />
      </Panel>
    );
  }

  return (
    <Panel title="Next Actions">
      <div className="grid gap-3">
        {actions.map((item, index) => (
          <div key={item.id || index} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="font-medium text-slate-900">{index + 1}. {item.title || item.id || "Readiness action"}</div>
            {item.remediation?.length ? (
              <ul className="mt-2 list-disc pl-5 text-sm text-slate-600">
                {item.remediation.map((line) => <li key={line}>{line}</li>)}
              </ul>
            ) : null}
          </div>
        ))}
      </div>
    </Panel>
  );
}

import type { AuditRun, Project } from "../../types";
import { Accordion, Panel } from "../../ui";

type Props = {
  auditRun?: AuditRun;
  lastResponse?: unknown;
  selectedProject?: Project;
};

export function RunContextPanel({ auditRun, lastResponse, selectedProject }: Props) {
  return (
    <Panel title="Run Context">
      <dl className="grid gap-3 text-sm">
        <InfoRow label="Project" value={selectedProject?.name || "-"} />
        <InfoRow label="Project ID" value={selectedProject?.project_id || "-"} />
        <InfoRow label="AuditRun ID" value={auditRun?.audit_run_id || "-"} />
        <InfoRow label="AuditRun Status" value={auditRun?.status || "-"} />
        <InfoRow label="Created At" value={auditRun?.created_at || "-"} />
      </dl>
      {Boolean(lastResponse) ? (
        <div className="mt-4">
          <Accordion items={[{ key: "last-response", title: "Last Response", children: <pre>{JSON.stringify(lastResponse, null, 2)}</pre> }]} />
        </div>
      ) : null}
    </Panel>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="min-w-0 truncate font-medium text-slate-800">{value}</dd>
    </div>
  );
}

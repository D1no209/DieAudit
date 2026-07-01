import type { AuditRun, Project } from "../../types";
import { Accordion, Badge, Panel } from "../../ui";
import { statusTone } from "../../utils/format";

type Props = {
  auditRun?: AuditRun;
  lastResponse?: unknown;
  selectedProject?: Project;
};

export function RunContextPanel({ auditRun, lastResponse, selectedProject }: Props) {
  return (
    <Panel title="Run Brief" dense>
      <dl className="grid gap-3 text-sm">
        <InfoRow label="Project" value={selectedProject?.name || "-"} badge={selectedProject?.status} />
        <InfoRow label="Project ID" value={selectedProject?.project_id || "-"} />
        <InfoRow label="AuditRun ID" value={auditRun?.audit_run_id || "-"} />
        <InfoRow label="Run Status" value={auditRun?.status || "-"} badge={auditRun?.status} />
        <InfoRow label="Snapshot" value={auditRun?.snapshot_id || "-"} />
        <InfoRow label="Created At" value={auditRun?.created_at || "-"} />
      </dl>
      <div className="mt-4 grid gap-2 rounded-lg border border-slate-300 bg-slate-50 p-3 text-xs">
        <div className="font-semibold uppercase text-slate-500">Config summary</div>
        <InfoRow label="Validation rounds" value={String(auditRun?.validator_rounds ?? "-")} />
        <InfoRow label="Validator parallel" value={String(auditRun?.max_parallel_validators ?? "-")} />
        <InfoRow label="External network" value={auditRun?.allow_external_network ? "allowed" : "blocked"} />
        <InfoRow label="Retain on failure" value={auditRun?.retain_runtime_on_failure ? "yes" : "no"} />
      </div>
      {Boolean(lastResponse) ? (
        <div className="mt-4">
          <Accordion items={[{ key: "last-response", title: "Last Response", children: <pre>{JSON.stringify(lastResponse, null, 2)}</pre> }]} />
        </div>
      ) : null}
    </Panel>
  );
}

function InfoRow({ badge, label, value }: { badge?: string; label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="flex min-w-0 items-center justify-end gap-1.5 truncate font-medium text-slate-800">
        <span className="truncate">{value}</span>
        {badge ? <Badge tone={statusTone(badge)}>{badge}</Badge> : null}
      </dd>
    </div>
  );
}

import type { Project } from "../../types";
import { Badge, Panel } from "../../ui";
import { statusTone } from "../../utils/format";

type Props = {
  selectedProject?: Project;
};

export function SelectedProjectPanel({ selectedProject }: Props) {
  return (
    <Panel title="Selected Project">
      <dl className="grid gap-3 text-sm">
        <InfoRow label="Name" value={selectedProject?.name || "-"} />
        <InfoRow label="Project ID" value={selectedProject?.project_id || "-"} />
        <InfoRow label="Source" value={selectedProject?.source_type || "-"} />
        <div className="flex items-center justify-between gap-3">
          <dt className="text-slate-500">Status</dt>
          <dd>{selectedProject?.status ? <Badge tone={statusTone(selectedProject.status)}>{selectedProject.status}</Badge> : "-"}</dd>
        </div>
      </dl>
      <p className="mt-4 text-sm text-slate-500">选择项目后，在 Audit Runs 页面启动审计闭环并查看运行结果。</p>
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

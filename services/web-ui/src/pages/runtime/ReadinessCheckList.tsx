import type { RuntimeReadinessCheck } from "../../types";
import { Alert, Badge } from "../../ui";
import { readinessColor, renderReadinessDescription } from "../../utils/format";

type Props = {
  checks: RuntimeReadinessCheck[];
  emptyText: string;
  type?: "success" | "warning";
};

export function ReadinessCheckList({ checks, emptyText, type = "success" }: Props) {
  if (checks.length === 0) {
    return <Alert tone={type} title={emptyText} />;
  }

  return (
    <div className="grid gap-3">
      {checks.map((item) => (
        <div key={item.id} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge tone={readinessColor(item.status)}>{item.status}</Badge>
            <span className="font-medium text-slate-800">{item.title}</span>
          </div>
          {renderReadinessDescription(item)}
        </div>
      ))}
    </div>
  );
}

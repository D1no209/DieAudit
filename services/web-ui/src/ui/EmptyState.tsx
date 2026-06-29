import { Inbox } from "lucide-react";

export function EmptyState({ description = "No data yet" }: { description?: React.ReactNode }) {
  return (
    <div className="flex min-h-28 flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
      <Inbox className="mb-2 h-5 w-5 text-slate-400" />
      {description}
    </div>
  );
}

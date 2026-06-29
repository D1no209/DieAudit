import type { AppView, NavigationGroup } from "../navigation";
import { cn } from "../ui/utils";

type Props = {
  activeView: AppView;
  groups: NavigationGroup[];
  onViewChange: (view: AppView) => void;
};

export function AppNavigation({ activeView, groups, onViewChange }: Props) {
  return (
    <aside className="sticky top-[77px] hidden h-[calc(100dvh-77px)] w-60 shrink-0 overflow-y-auto border-r border-slate-200 bg-white px-3 py-4 lg:block">
      {groups.map((group) => (
        <div key={group.key} className="mb-5">
          <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{group.label}</div>
          <div className="grid gap-1">
            {group.items.map((item) => (
              <button
                key={item.key}
                type="button"
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition",
                  activeView === item.key ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
                )}
                onClick={() => onViewChange(item.key as AppView)}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </div>
        </div>
      ))}
    </aside>
  );
}

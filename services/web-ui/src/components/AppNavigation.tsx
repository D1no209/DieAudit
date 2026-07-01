import type { AppView, NavigationGroup } from "../navigation";
import { cn } from "../ui/utils";

type Props = {
  activeView: AppView;
  groups: NavigationGroup[];
  onViewChange: (view: AppView) => void;
};

export function AppNavigation({ activeView, groups, onViewChange }: Props) {
  return (
    <aside className="sticky top-[57px] hidden h-[calc(100dvh-57px)] w-64 shrink-0 overflow-y-auto border-r border-slate-300 bg-slate-50 px-3 py-4 lg:block">
      {groups.map((group) => (
        <div key={group.key} className="mb-4">
          <div className="px-2 pb-1.5 text-[11px] font-semibold uppercase text-slate-500">{group.label}</div>
          <div className="grid gap-1">
            {group.items.map((item) => (
              <button
                key={item.key}
                type="button"
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition",
                  activeView === item.key
                    ? "border border-cyan-200 bg-white text-cyan-900 shadow-sm shadow-slate-200/70"
                    : "border border-transparent text-slate-600 hover:bg-white hover:text-slate-950",
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

import { Bug, LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import type { AppView } from "../navigation";
import type { NavigationItem } from "../navigation";
import type { AuthPrincipal } from "../types";
import { Button } from "../ui";
import { cn } from "../ui/utils";

type Props = {
  activeView: AppView;
  authPrincipal?: AuthPrincipal;
  authEnabled?: boolean;
  navigationItems: NavigationItem[];
  onLogout: () => void;
  onRefresh: () => void;
  onViewChange: (view: AppView) => void;
};

export function AppHeader({
  activeView,
  authEnabled,
  authPrincipal,
  navigationItems,
  onLogout,
  onRefresh,
  onViewChange,
}: Props) {
  const principalLabel = authPrincipal?.name || authPrincipal?.key_id || authPrincipal?.source || "已登录";

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-700 text-white shadow-sm">
            <Bug className="h-5 w-5" />
          </span>
          <div>
            <h1 className="m-0 text-lg font-semibold leading-tight text-slate-950">DieAudit</h1>
            <p className="m-0 text-xs text-slate-500">多 Agent 代码审计运行台</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {authEnabled ? (
            <div className="flex h-9 max-w-64 items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 text-sm text-emerald-800">
              <ShieldCheck className="h-4 w-4 shrink-0" />
              <span className="truncate">{principalLabel}</span>
            </div>
          ) : null}
          <Button icon={<RefreshCw className="h-4 w-4" />} onClick={onRefresh}>刷新</Button>
          {authEnabled ? (
            <Button icon={<LogOut className="h-4 w-4" />} onClick={onLogout}>退出</Button>
          ) : null}
        </div>
      </div>
      <nav className="mx-auto mt-3 flex max-w-[1440px] gap-1 overflow-x-auto lg:hidden" aria-label="Mobile navigation">
        {navigationItems.map((item) => (
          <button
            key={item.key}
            type="button"
            className={cn(
              "inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-600",
              activeView === item.key ? "bg-blue-50 text-blue-700" : "hover:bg-slate-100 hover:text-slate-950",
            )}
            onClick={() => onViewChange(item.key as AppView)}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </nav>
    </header>
  );
}

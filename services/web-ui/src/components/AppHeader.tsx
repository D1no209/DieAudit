import { Bug, Circle, LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import type { AppView } from "../navigation";
import type { NavigationItem } from "../navigation";
import type { ApiHealth, AuditRun, AuthPrincipal, DockerHealth, Project, RuntimeReadiness } from "../types";
import { Badge, Button } from "../ui";
import { cn } from "../ui/utils";
import { statusTone } from "../utils/format";

type Props = {
  activeView: AppView;
  apiHealth?: ApiHealth;
  authPrincipal?: AuthPrincipal;
  authEnabled?: boolean;
  dockerHealth?: DockerHealth;
  navigationItems: NavigationItem[];
  onLogout: () => void;
  onRefresh: () => void;
  onViewChange: (view: AppView) => void;
  runtimeReadiness?: RuntimeReadiness;
  selectedAuditRun?: AuditRun;
  selectedProject?: Project;
};

export function AppHeader({
  activeView,
  apiHealth,
  authEnabled,
  authPrincipal,
  dockerHealth,
  navigationItems,
  onLogout,
  onRefresh,
  onViewChange,
  runtimeReadiness,
  selectedAuditRun,
  selectedProject,
}: Props) {
  const principalLabel = authPrincipal?.name || authPrincipal?.key_id || authPrincipal?.source || "已登录";
  const refreshedAt = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date());

  return (
    <header className="sticky top-0 z-30 border-b border-slate-300 bg-white/95 px-3 py-2 backdrop-blur sm:px-4 lg:px-6">
      <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-cyan-900 bg-cyan-900 text-white">
            <Bug className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <h1 className="m-0 text-base font-semibold leading-tight text-slate-950">DieAudit</h1>
            <p className="m-0 truncate text-xs text-slate-500">Audit workbench</p>
          </div>
          <div className="hidden min-w-0 items-center gap-2 border-l border-slate-200 pl-3 md:flex">
            <ContextPill label="Project" value={selectedProject?.name || "none"} tone={statusTone(selectedProject?.status)} />
            <ContextPill label="Run" value={selectedAuditRun?.audit_run_id || "none"} tone={statusTone(selectedAuditRun?.status)} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill label="BFF" ok={Boolean(apiHealth?.ok)} fallback={apiHealth?.service || "unknown"} />
          <StatusPill label="Runtime" ok={Boolean(dockerHealth?.ok)} fallback={dockerHealth?.status || "unknown"} />
          <Badge tone={runtimeReadiness?.ok ? "success" : runtimeReadiness?.status ? statusTone(runtimeReadiness.status) : "neutral"}>
            readiness {runtimeReadiness?.status || "unknown"}
          </Badge>
          <Badge>refresh {refreshedAt}</Badge>
          {authEnabled ? (
            <div className="flex h-8 max-w-48 items-center gap-2 rounded-md border border-emerald-300 bg-emerald-50 px-2.5 text-xs font-semibold text-emerald-900">
              <ShieldCheck className="h-4 w-4 shrink-0" />
              <span className="truncate">{principalLabel}</span>
            </div>
          ) : null}
          <Button size="sm" icon={<RefreshCw className="h-4 w-4" />} onClick={onRefresh}>刷新</Button>
          {authEnabled ? (
            <Button size="sm" icon={<LogOut className="h-4 w-4" />} onClick={onLogout}>退出</Button>
          ) : null}
        </div>
      </div>
      <nav className="mx-auto mt-2 flex max-w-[1500px] gap-1 overflow-x-auto lg:hidden" aria-label="Mobile navigation">
        {navigationItems.map((item) => (
          <button
            key={item.key}
            type="button"
            className={cn(
              "inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-600",
              activeView === item.key ? "bg-cyan-50 text-cyan-900" : "hover:bg-slate-100 hover:text-slate-950",
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

function ContextPill({ label, tone, value }: { label: string; tone: React.ComponentProps<typeof Badge>["tone"]; value: string }) {
  return (
    <div className="flex min-w-0 items-center gap-1.5 text-xs">
      <span className="text-slate-500">{label}</span>
      <Badge tone={tone} className="max-w-52 truncate">{value}</Badge>
    </div>
  );
}

function StatusPill({ fallback, label, ok }: { fallback: string; label: string; ok: boolean }) {
  return (
    <Badge tone={ok ? "success" : "warning"}>
      <Circle className={cn("h-2 w-2 fill-current", ok ? "text-emerald-700" : "text-amber-700")} />
      {label} {ok ? "ok" : fallback}
    </Badge>
  );
}

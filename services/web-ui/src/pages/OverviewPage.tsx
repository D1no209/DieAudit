import { Activity, Bug, Container, FolderOpen, KeyRound, Network, ShieldCheck } from "lucide-react";
import type { ApiHealth, AuthStatus, DockerHealth, ManagedRuntime, RuntimeReadiness, SandboxCapabilities } from "../types";
import { Alert, Badge, MetricCard, PageHeader, Panel } from "../ui";
import { statusTone } from "../utils/format";

type Props = {
  apiHealth?: ApiHealth;
  authStatus?: AuthStatus;
  dockerHealth?: DockerHealth;
  findingsCount: number;
  managedRuntime?: ManagedRuntime;
  projectsCount: number;
  runtimeReadiness?: RuntimeReadiness;
  sandboxCapabilities?: SandboxCapabilities;
};

export function OverviewPage({
  apiHealth,
  authStatus,
  dockerHealth,
  findingsCount,
  managedRuntime,
  projectsCount,
  runtimeReadiness,
  sandboxCapabilities,
}: Props) {
  const firstBlockingCheck = runtimeReadiness?.blocking_checks?.[0] || runtimeReadiness?.checks?.find((item) => item.status === "fail");
  const firstNextAction = runtimeReadiness?.next_actions?.[0];

  return (
    <>
      <PageHeader title="Overview" />
      {!runtimeReadiness?.ok && firstNextAction ? (
        <Alert
          className="mb-5"
          tone="danger"
          title={firstNextAction.title || "Production readiness blocker"}
          description={firstNextAction.remediation?.[0] || "Open Runtime > Readiness for the full remediation checklist."}
        />
      ) : null}

      <div className="mb-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard icon={<Activity className="h-5 w-5" />} label="Web API" value={apiHealth?.ok ? "Healthy" : "Unknown"} />
        <MetricCard
          icon={<KeyRound className="h-5 w-5" />}
          label="API Auth"
          value={authStatus?.enabled ? "Enabled" : "Disabled"}
          detail={!authStatus?.enabled ? <span className="text-red-700">Set DIEAUDIT_API_KEY before production use.</span> : null}
        />
        <MetricCard
          icon={<ShieldCheck className="h-5 w-5" />}
          label="Production Readiness"
          value={runtimeReadiness?.ok ? "Ready" : "Not Ready"}
          detail={
            <span className="grid gap-1">
              <span>fail {runtimeReadiness?.summary?.fail ?? "-"} / warn {runtimeReadiness?.summary?.warn ?? "-"} / pass {runtimeReadiness?.summary?.pass ?? "-"}</span>
              {!runtimeReadiness?.ok && firstBlockingCheck ? <span>{firstBlockingCheck.title}</span> : null}
            </span>
          }
        />
        <MetricCard icon={<Network className="h-5 w-5" />} label="Docker Runtime" value={dockerHealth?.ok ? "Ready" : "Unknown"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
        <Panel title="Audit Surface">
          <div className="grid gap-4 sm:grid-cols-3">
            <MetricInline icon={<FolderOpen className="h-4 w-4" />} label="Projects" value={projectsCount} />
            <MetricInline icon={<Bug className="h-4 w-4" />} label="Findings" value={findingsCount} />
            <MetricInline icon={<Container className="h-4 w-4" />} label="Runtime Containers" value={managedRuntime?.summary?.container_count ?? 0} />
          </div>
        </Panel>
        <Panel title="Sandbox">
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone={sandboxCapabilities?.sandbox_execution_available ? "success" : "danger"}>
              {sandboxCapabilities?.sandbox_execution_available ? "Ready" : "Unavailable"}
            </Badge>
            <span className="text-sm text-slate-600">Runtime {sandboxCapabilities?.requested_runtime || "-"}</span>
            {sandboxCapabilities?.requested_runtime === "runc" && !sandboxCapabilities?.strong_isolation_available ? (
              <Badge tone={sandboxCapabilities?.allow_runc_sandbox ? "warning" : "danger"}>
                {sandboxCapabilities?.allow_runc_sandbox ? "Weak runc isolation enabled" : "Strong isolation unavailable"}
              </Badge>
            ) : null}
          </div>
          {sandboxCapabilities?.warnings?.[0] ? <p className="mt-3 text-sm text-slate-500">{sandboxCapabilities.warnings[0]}</p> : null}
        </Panel>
      </div>
    </>
  );
}

function MetricInline({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">{icon}{label}</div>
      <div className="mt-2 text-xl font-semibold text-slate-950">{value}</div>
    </div>
  );
}

import * as dashboardApi from "../../client/dashboardApi";
import type { SandboxPocFormValues, SandboxServiceFormValues } from "../../types";
import { toast } from "../../ui/toast";
import type { DashboardStateController } from "../useDashboardState";

type DashboardRunner = {
  refreshAuditRun: (auditRunId: string) => Promise<void>;
  runAction: (action: () => Promise<void>) => Promise<void>;
};

export function useRuntimeActions(dashboardState: DashboardStateController, runner: DashboardRunner) {
  const {
    auditRun,
    sandboxCapabilities,
    sandboxTarget,
    selectedFinding,
    setLastResponse,
    setManagedRuntime,
    setSandboxTarget,
    setSelectedFinding,
    setStorageSummary,
  } = dashboardState;

  function sandboxUnavailableMessage() {
    return (
      sandboxCapabilities?.reason ||
      sandboxCapabilities?.warnings?.[0] ||
      "Sandbox execution is not available. Verify Docker is reachable and the configured sandbox runtime is available."
    );
  }

  function ensureSandboxExecutionAvailable() {
    if (sandboxCapabilities?.sandbox_execution_available) {
      return true;
    }
    toast.error(sandboxUnavailableMessage());
    return false;
  }

  async function refreshManagedRuntime() {
    const managed = await dashboardApi.getManagedRuntime();
    setManagedRuntime(managed);
  }

  function parseCommand(value: string) {
    const trimmed = value.trim();
    if (!trimmed) {
      return [];
    }
    if (trimmed.startsWith("[")) {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed) && parsed.every((item) => typeof item === "string")) {
        return parsed;
      }
      throw new Error("Command JSON must be an array of strings.");
    }
    return trimmed.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  }

  async function runSandboxPoc(values: SandboxPocFormValues) {
    if (!auditRun) {
      toast.error("请先创建 AuditRun");
      return;
    }
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    await runner.runAction(async () => {
      const command = parseCommand(values.command);
      const result = await dashboardApi.runSandboxPoc(auditRun.audit_run_id, {
        image: values.image,
        command,
        allow_external_network: false,
        timeout_seconds: values.timeout_seconds ?? 120,
        expected_exit_code: values.expected_exit_code ?? 0,
        mount_workspace: values.mount_workspace ?? true,
        target_url: values.target_url || undefined,
        retain_runtime_on_failure: values.retain_runtime_on_failure ?? false,
        allow_weak_isolation: false,
      });
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
      await refreshManagedRuntime();
    });
  }

  async function startSandboxService(values: SandboxServiceFormValues) {
    if (!auditRun) {
      toast.error("请先创建 AuditRun");
      return;
    }
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    await runner.runAction(async () => {
      const command = parseCommand(values.command);
      const result = await dashboardApi.startSandboxService(auditRun.audit_run_id, {
        image: values.image,
        command,
        service_name: values.service_name || "target",
        port: values.port ?? 8080,
        allow_external_network: false,
        mount_workspace: values.mount_workspace ?? true,
        retain_runtime_on_failure: values.retain_runtime_on_failure ?? true,
        healthcheck_path: values.healthcheck_path || undefined,
        startup_timeout_seconds: values.startup_timeout_seconds ?? 30,
        allow_weak_isolation: false,
      });
      setSandboxTarget({ network: result.network, target_url: result.target_url });
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
      await refreshManagedRuntime();
    });
  }

  async function runSandboxTargetPoc(values: SandboxPocFormValues) {
    if (!auditRun) {
      toast.error("请先创建 AuditRun");
      return;
    }
    if (!sandboxTarget) {
      toast.error("请先启动 Sandbox Service");
      return;
    }
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    await runner.runAction(async () => {
      const command = parseCommand(values.command);
      const result = await dashboardApi.runSandboxPoc(auditRun.audit_run_id, {
        image: values.image,
        command,
        network_name: sandboxTarget.network,
        target_url: values.target_url || sandboxTarget.target_url,
        allow_external_network: false,
        timeout_seconds: values.timeout_seconds ?? 120,
        expected_exit_code: values.expected_exit_code ?? 0,
        mount_workspace: values.mount_workspace ?? true,
        retain_runtime_on_failure: values.retain_runtime_on_failure ?? false,
        allow_weak_isolation: false,
      });
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
      await refreshManagedRuntime();
    });
  }

  async function runFindingPoc(values: SandboxPocFormValues) {
    if (!selectedFinding || !auditRun) {
      return;
    }
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    const findingId = selectedFinding.finding.finding_id;
    await runner.runAction(async () => {
      const command = parseCommand(values.command);
      const result = await dashboardApi.runFindingPoc(findingId, {
        image: values.image,
        command,
        allow_external_network: false,
        timeout_seconds: values.timeout_seconds ?? 120,
        expected_exit_code: values.expected_exit_code ?? 0,
        mount_workspace: values.mount_workspace ?? true,
        retain_runtime_on_failure: values.retain_runtime_on_failure ?? false,
        allow_weak_isolation: false,
      });
      setLastResponse(result);
      setSelectedFinding(result.finding);
      await runner.refreshAuditRun(auditRun.audit_run_id);
      await refreshManagedRuntime();
    });
  }

  async function cleanupExpiredRuntime() {
    await runner.runAction(async () => {
      const result = await dashboardApi.cleanupExpiredRuntime();
      setLastResponse(result);
      await refreshManagedRuntime();
      if (auditRun) {
        await runner.refreshAuditRun(auditRun.audit_run_id);
      }
    });
  }

  async function previewLocalStorageCleanup() {
    await runner.runAction(async () => {
      const result = await dashboardApi.previewLocalStorageCleanup();
      setLastResponse(result);
      const summary = await dashboardApi.getStorageSummary();
      setStorageSummary(summary);
    });
  }

  return {
    cleanupExpiredRuntime,
    previewLocalStorageCleanup,
    runFindingPoc,
    runSandboxPoc,
    runSandboxTargetPoc,
    sandboxUnavailableMessage,
    startSandboxService,
  };
}

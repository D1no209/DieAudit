import { message } from "antd";
import * as dashboardApi from "../../client/dashboardApi";
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
      "Sandbox execution is not available. Configure gVisor/Kata or an approved sandbox runtime before running PoC containers."
    );
  }

  function ensureSandboxExecutionAvailable() {
    if (sandboxCapabilities?.sandbox_execution_available) {
      return true;
    }
    message.error(sandboxUnavailableMessage());
    return false;
  }

  async function refreshManagedRuntime() {
    const managed = await dashboardApi.getManagedRuntime();
    setManagedRuntime(managed);
  }

  async function runPocSmoke() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.runSandboxPoc(auditRun.audit_run_id, {
        image: "python:3.12-slim",
        command: [
          "python",
          "-c",
          "import os, json; print('dieaudit poc smoke'); print(json.dumps(os.listdir('/workspace')[:20] if os.path.exists('/workspace') else []))",
        ],
        allow_external_network: false,
        timeout_seconds: 120,
        allow_weak_isolation: false,
      });
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
      await refreshManagedRuntime();
    });
  }

  async function startSandboxService() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.startSandboxService(auditRun.audit_run_id, {
        image: "python:3.12-slim",
        command: ["python", "-m", "http.server", "8080", "--directory", "/workspace"],
        service_name: "target",
        port: 8080,
        allow_external_network: false,
        retain_runtime_on_failure: true,
        startup_timeout_seconds: 30,
        allow_weak_isolation: false,
      });
      setSandboxTarget({ network: result.network, target_url: result.target_url });
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
      await refreshManagedRuntime();
    });
  }

  async function runSandboxTargetPoc() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    if (!sandboxTarget) {
      message.error("请先启动 Sandbox Service");
      return;
    }
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.runSandboxPoc(auditRun.audit_run_id, {
        image: "python:3.12-slim",
        command: [
          "python",
          "-c",
          "import os, urllib.request; url=os.environ['TARGET_URL']; r=urllib.request.urlopen(url, timeout=5); print(url); print(r.status); print(r.read(120).decode('utf-8', 'replace'))",
        ],
        network_name: sandboxTarget.network,
        target_url: sandboxTarget.target_url,
        allow_external_network: false,
        timeout_seconds: 120,
        expected_exit_code: 0,
        allow_weak_isolation: false,
      });
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
      await refreshManagedRuntime();
    });
  }

  async function runFindingPoc() {
    if (!selectedFinding || !auditRun) {
      return;
    }
    if (!ensureSandboxExecutionAvailable()) {
      return;
    }
    const findingId = selectedFinding.finding.finding_id;
    await runner.runAction(async () => {
      const result = await dashboardApi.runFindingPoc(findingId, {
        image: "python:3.12-slim",
        command: [
          "python",
          "-c",
          "import os, json; print('dieaudit finding poc smoke'); print(json.dumps({'workspace': os.listdir('/workspace')[:20] if os.path.exists('/workspace') else [], 'artifact_dir': os.environ.get('ARTIFACT_DIR')}))",
        ],
        allow_external_network: false,
        timeout_seconds: 120,
        expected_exit_code: 0,
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
    runPocSmoke,
    runSandboxTargetPoc,
    sandboxUnavailableMessage,
    startSandboxService,
  };
}

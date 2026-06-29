import { API_KEY_STORAGE_KEY } from "../../api";
import * as dashboardApi from "../../client/dashboardApi";
import type { AppView } from "../../navigation";
import { toast } from "../../ui/toast";
import { parseCsvList, parseScopes } from "../../utils/format";
import type { DashboardStateController } from "../useDashboardState";

type DashboardRunner = {
  refreshCurrentView: (view: AppView) => Promise<void>;
  runAction: (action: () => Promise<void>) => Promise<void>;
};

export function useAdminActions(dashboardState: DashboardStateController, runner: DashboardRunner, activeView: AppView) {
  const {
    apiKey,
    setApiKeys,
    setLastResponse,
    setPlatformAuditEvents,
  } = dashboardState;

  async function cleanupPlatformAuditEvents() {
    await runner.runAction(async () => {
      const result = await dashboardApi.cleanupPlatformAuditEvents();
      setLastResponse(result);
      const rows = await dashboardApi.listPlatformAuditEvents();
      setPlatformAuditEvents(rows);
    });
  }

  async function createManagedApiKey(values: { name: string; scopes?: string; project_ids?: string; audit_run_ids?: string }) {
    await runner.runAction(async () => {
      const projectIds = parseCsvList(values.project_ids);
      const auditRunIds = parseCsvList(values.audit_run_ids);
      const result = await dashboardApi.createManagedApiKey({
        name: values.name,
        scopes: parseScopes(values.scopes),
        metadata: {
          ...(projectIds.length ? { project_ids: projectIds } : {}),
          ...(auditRunIds.length ? { audit_run_ids: auditRunIds } : {}),
        },
      });
      setLastResponse(result);
      const rows = await dashboardApi.listApiKeys();
      setApiKeys(rows);
    });
  }

  async function deactivateManagedApiKey(keyId: string) {
    await runner.runAction(async () => {
      const result = await dashboardApi.deactivateManagedApiKey(keyId);
      setLastResponse(result);
      const rows = await dashboardApi.listApiKeys();
      setApiKeys(rows);
    });
  }

  function saveApiKey() {
    const normalized = apiKey.trim();
    if (normalized) {
      window.localStorage.setItem(API_KEY_STORAGE_KEY, normalized);
      toast.success("API Key saved locally");
    } else {
      window.localStorage.removeItem(API_KEY_STORAGE_KEY);
      toast.warning("API Key removed");
    }
    runner.refreshCurrentView(activeView);
  }

  return { cleanupPlatformAuditEvents, createManagedApiKey, deactivateManagedApiKey, saveApiKey };
}

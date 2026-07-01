import { clearStoredApiKey, storeApiKey } from "../../api";
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
    clearProtectedState,
    setAgentModelConfig,
    setApiKeys,
    setApiKey,
    setAuthPrincipal,
    setError,
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

  async function updateAgentModelConfig(values: Parameters<typeof dashboardApi.updateAgentModelConfig>[0]) {
    await runner.runAction(async () => {
      const result = await dashboardApi.updateAgentModelConfig(values);
      setAgentModelConfig(result);
      setLastResponse(result);
      toast.success("Agent 模型配置已保存");
    });
  }

  async function login(credentials: { username: string; password: string }) {
    const username = credentials.username.trim();
    if (!username || !credentials.password) {
      setError("请输入账号和密码");
      return;
    }
    await runner.runAction(async () => {
      const authMe = await dashboardApi.loginWithPassword(username, credentials.password);
      if (!authMe.authenticated) {
        throw new Error("登录凭证未通过验证");
      }
      if (!authMe.access_token) {
        throw new Error("登录成功但服务端未返回内部访问令牌");
      }
      storeApiKey(authMe.access_token);
      setApiKey(authMe.access_token);
      setAuthPrincipal(authMe.principal || undefined);
      toast.success("登录成功");
      await runner.refreshCurrentView(activeView);
    });
  }

  function logout() {
    clearStoredApiKey();
    setApiKey("");
    setAuthPrincipal(undefined);
    clearProtectedState();
    setError(undefined);
    toast.success("已退出登录");
    runner.refreshCurrentView(activeView);
  }

  return { cleanupPlatformAuditEvents, createManagedApiKey, deactivateManagedApiKey, login, logout, updateAgentModelConfig };
}

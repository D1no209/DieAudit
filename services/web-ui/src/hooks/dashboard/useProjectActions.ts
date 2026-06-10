import { message } from "antd";
import * as dashboardApi from "../../client/dashboardApi";
import type { DashboardStateController } from "../useDashboardState";

type DashboardRunner = {
  refresh: () => Promise<void>;
  refreshAuditRun: (auditRunId: string) => Promise<void>;
  runAction: (action: () => Promise<void>) => Promise<void>;
};

export function useProjectActions(dashboardState: DashboardStateController, runner: DashboardRunner) {
  const {
    gitForm,
    selectedProjectId,
    setLastResponse,
    setSelectedProjectId,
    setZipFiles,
    zipFiles,
    zipForm,
  } = dashboardState;

  async function createGitProject(values: { name: string; git_url: string; ref?: string }) {
    await runner.runAction(async () => {
      const result = await dashboardApi.createGitProject(values);
      setLastResponse(result);
      setSelectedProjectId(result.project.project_id);
      gitForm.resetFields();
      await runner.refresh();
    });
  }

  async function uploadZipProject(values: { name: string }) {
    const zipFile = zipFiles[0]?.originFileObj;
    if (!zipFile) {
      message.error("请选择 zip 文件");
      return;
    }
    await runner.runAction(async () => {
      const formData = new FormData();
      formData.append("name", values.name);
      formData.append("file", zipFile);
      const result = await dashboardApi.uploadZipProject(formData);
      setLastResponse(result);
      setSelectedProjectId(result.project.project_id);
      zipForm.resetFields();
      setZipFiles([]);
      await runner.refresh();
    });
  }

  async function startAudit() {
    if (!selectedProjectId) {
      message.error("请选择项目");
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.createAuditRun(selectedProjectId);
      setLastResponse(result);
      await runner.refreshAuditRun(result.audit_run.audit_run_id);
    });
  }

  return { createGitProject, startAudit, uploadZipProject };
}

import * as dashboardApi from "../../client/dashboardApi";
import type { CreateAuditRunPayload } from "../../types";
import { toast } from "../../ui/toast";
import type { DashboardStateController } from "../useDashboardState";

type DashboardRunner = {
  refreshProjects: (preferredProjectId?: string) => Promise<void>;
  refreshAuditRun: (auditRunId: string) => Promise<void>;
  runAction: (action: () => Promise<void>) => Promise<void>;
};

export function useProjectActions(dashboardState: DashboardStateController, runner: DashboardRunner) {
  const {
    selectedProjectId,
    setLastResponse,
    setSelectedProjectId,
    setZipFiles,
    zipFiles,
  } = dashboardState;

  async function createGitProject(values: { name: string; git_url: string; ref?: string }) {
    await runner.runAction(async () => {
      const result = await dashboardApi.createGitProject(values);
      setLastResponse(result);
      setSelectedProjectId(result.project.project_id);
      await runner.refreshProjects(result.project.project_id);
    });
  }

  async function uploadZipProject(values: { name: string }) {
    const zipFile = zipFiles[0];
    if (!zipFile) {
      toast.error("请选择 zip 文件");
      return;
    }
    await runner.runAction(async () => {
      const formData = new FormData();
      formData.append("name", values.name);
      formData.append("file", zipFile);
      const result = await dashboardApi.uploadZipProject(formData);
      setLastResponse(result);
      setSelectedProjectId(result.project.project_id);
      setZipFiles([]);
      await runner.refreshProjects(result.project.project_id);
    });
  }

  async function startAudit(payload: CreateAuditRunPayload) {
    if (!selectedProjectId) {
      toast.error("请选择项目");
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.createAuditRun(selectedProjectId, payload);
      setLastResponse(result);
      await runner.refreshAuditRun(result.audit_run.audit_run_id);
    });
  }

  return { createGitProject, startAudit, uploadZipProject };
}

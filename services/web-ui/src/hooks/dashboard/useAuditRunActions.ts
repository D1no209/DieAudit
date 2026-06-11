import { message } from "antd";
import * as dashboardApi from "../../client/dashboardApi";
import { hashFromAppView } from "../../navigation";
import type { ArtifactRef, ContainerRow } from "../../types";
import { artifactFileName, artifactUrl } from "../../utils/format";
import type { DashboardStateController } from "../useDashboardState";

type DashboardRunner = {
  refreshAuditRun: (auditRunId: string) => Promise<void>;
  runAction: (action: () => Promise<void>) => Promise<void>;
};

export function useAuditRunActions(dashboardState: DashboardStateController, runner: DashboardRunner) {
  const {
    auditRun,
    setAgentEvents,
    setArtifactPreview,
    setContainerLogs,
    setLastResponse,
    setSelectedFinding,
  } = dashboardState;

  async function runSca() {
    if (!auditRun) {
      message.error("请先启动 AuditRun");
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.runSca(auditRun.audit_run_id);
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function runPipeline() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.runPipeline(auditRun.audit_run_id);
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function runJudge() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.runJudge(auditRun.audit_run_id);
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function generateReport() {
    if (!auditRun) {
      message.error("请先创建 AuditRun");
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.generateReport(auditRun.audit_run_id);
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function openArtifact(artifact?: ArtifactRef, fallbackPath?: string) {
    const url = artifactUrl(artifact, fallbackPath);
    if (!url) {
      message.warning("Artifact is not available");
      return;
    }
    await runner.runAction(async () => {
      const blob = await dashboardApi.fetchArtifactBlob(url);
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = artifactFileName(artifact, fallbackPath);
      link.rel = "noopener";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
    });
  }

  async function previewArtifact(artifact?: ArtifactRef, fallbackPath?: string) {
    const url = artifactUrl(artifact, fallbackPath);
    if (!url) {
      message.warning("Artifact is not available");
      return;
    }
    await runner.runAction(async () => {
      const blob = await dashboardApi.fetchArtifactBlob(url);
      const body = await blob.text();
      setArtifactPreview({ title: artifactFileName(artifact, fallbackPath), body });
    });
  }

  async function openFinding(findingId: string) {
    await runner.runAction(async () => {
      const result = await dashboardApi.getFinding(findingId);
      setSelectedFinding(result);
      window.location.hash = hashFromAppView("finding-review");
    });
  }

  async function openAgentEvents(agentRunId: string) {
    if (!auditRun) {
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.getAgentEvents(auditRun.audit_run_id, agentRunId);
      setAgentEvents(result);
    });
  }

  async function openContainerLogs(row: ContainerRow) {
    if (!auditRun) {
      return;
    }
    await runner.runAction(async () => {
      const text = await dashboardApi.getContainerLogs(auditRun.audit_run_id, row.Id);
      setContainerLogs({ title: row.container_name || row.Names?.[0]?.replace("/", "") || row.Id.slice(0, 12), body: text });
    });
  }

  async function cleanup() {
    if (!auditRun) {
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.cleanupAuditRun(auditRun.audit_run_id);
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
    });
  }

  async function cancelAuditRun() {
    if (!auditRun) {
      return;
    }
    await runner.runAction(async () => {
      const result = await dashboardApi.cancelAuditRun(auditRun.audit_run_id);
      setLastResponse(result);
      await runner.refreshAuditRun(auditRun.audit_run_id);
    });
  }

  return {
    cancelAuditRun,
    cleanup,
    generateReport,
    openAgentEvents,
    openArtifact,
    openContainerLogs,
    openFinding,
    previewArtifact,
    runJudge,
    runPipeline,
    runSca,
  };
}

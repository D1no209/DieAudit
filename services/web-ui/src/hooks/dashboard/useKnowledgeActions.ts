import { message } from "antd";
import * as dashboardApi from "../../client/dashboardApi";
import type { DashboardStateController } from "../useDashboardState";

type DashboardRunner = {
  runAction: (action: () => Promise<void>) => Promise<void>;
};

export function useKnowledgeActions(dashboardState: DashboardStateController, runner: DashboardRunner) {
  const {
    knowledgeFiles,
    knowledgeUploadForm,
    selectedProjectId,
    setKnowledgeDocuments,
    setKnowledgeFiles,
    setKnowledgeMatches,
    setLastResponse,
  } = dashboardState;

  async function uploadKnowledgeDocument(values: { title: string; scope?: string; project_id?: string }) {
    const knowledgeFile = knowledgeFiles[0]?.originFileObj;
    if (!knowledgeFile) {
      message.error("请选择知识库文档");
      return;
    }
    await runner.runAction(async () => {
      const scope = (values.scope || "global").trim().toLowerCase();
      const formData = new FormData();
      formData.append("title", values.title);
      formData.append("scope", scope);
      if (scope === "project" && values.project_id) {
        formData.append("project_id", values.project_id);
      }
      formData.append("file", knowledgeFile);
      const result = await dashboardApi.uploadKnowledgeDocument(formData);
      setLastResponse(result);
      knowledgeUploadForm.resetFields();
      setKnowledgeFiles([]);
      const rows = await dashboardApi.listKnowledgeDocuments();
      setKnowledgeDocuments(rows);
    });
  }

  async function searchKnowledge(values: { query: string; project_id?: string; limit?: string }) {
    await runner.runAction(async () => {
      const result = await dashboardApi.searchKnowledge({
        query: values.query,
        project_id: values.project_id || selectedProjectId || undefined,
        include_global: true,
        limit: Number(values.limit || 8),
      });
      setLastResponse(result);
      setKnowledgeMatches(result.matches || []);
    });
  }

  async function reindexKnowledgeDocument(documentId: string) {
    await runner.runAction(async () => {
      const result = await dashboardApi.reindexKnowledgeDocument(documentId);
      setLastResponse(result);
      const rows = await dashboardApi.listKnowledgeDocuments();
      setKnowledgeDocuments(rows);
    });
  }

  async function deleteKnowledgeDocument(documentId: string) {
    await runner.runAction(async () => {
      const result = await dashboardApi.deleteKnowledgeDocument(documentId);
      setLastResponse(result);
      const rows = await dashboardApi.listKnowledgeDocuments();
      setKnowledgeDocuments(rows);
      setKnowledgeMatches((items) => items.filter((item) => item.document_id !== documentId));
    });
  }

  return { deleteKnowledgeDocument, reindexKnowledgeDocument, searchKnowledge, uploadKnowledgeDocument };
}

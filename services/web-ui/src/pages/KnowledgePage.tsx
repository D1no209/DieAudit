import type { ColumnsType } from "antd/es/table";
import type { FormInstance } from "antd/es/form";
import type { UploadFile } from "antd/es/upload/interface";
import type { KnowledgeDocument, KnowledgeMatch } from "../types";
import { PageHeader } from "../components/PageHeader";
import { KnowledgeDocumentsPanel } from "./knowledge/KnowledgeDocumentsPanel";
import { KnowledgeSearchPanel } from "./knowledge/KnowledgeSearchPanel";
import { KnowledgeUploadPanel } from "./knowledge/KnowledgeUploadPanel";

type Props = {
  knowledgeColumns: ColumnsType<KnowledgeDocument>;
  knowledgeDocuments: KnowledgeDocument[];
  knowledgeFiles: UploadFile[];
  knowledgeMatches: KnowledgeMatch[];
  knowledgeSearchForm: FormInstance;
  knowledgeUploadForm: FormInstance;
  loading: boolean;
  selectedProjectId?: string;
  onSearchKnowledge: (values: { query: string; project_id?: string; limit?: string }) => void;
  onSetKnowledgeFiles: (files: UploadFile[]) => void;
  onUploadKnowledgeDocument: (values: { title: string; scope?: string; project_id?: string }) => void;
};

export function KnowledgePage({
  knowledgeColumns,
  knowledgeDocuments,
  knowledgeFiles,
  knowledgeMatches,
  knowledgeSearchForm,
  knowledgeUploadForm,
  loading,
  selectedProjectId,
  onSearchKnowledge,
  onSetKnowledgeFiles,
  onUploadKnowledgeDocument,
}: Props) {
  return (
    <>
      <PageHeader title="Knowledge" />
      <div className="knowledge-grid section">
        <div className="panel-stack">
          <KnowledgeUploadPanel
            files={knowledgeFiles}
            form={knowledgeUploadForm}
            loading={loading}
            selectedProjectId={selectedProjectId}
            onSetFiles={onSetKnowledgeFiles}
            onUpload={onUploadKnowledgeDocument}
          />
          <KnowledgeDocumentsPanel columns={knowledgeColumns} documents={knowledgeDocuments} />
        </div>
        <KnowledgeSearchPanel
          form={knowledgeSearchForm}
          loading={loading}
          matches={knowledgeMatches}
          selectedProjectId={selectedProjectId}
          onSearch={onSearchKnowledge}
        />
      </div>
    </>
  );
}

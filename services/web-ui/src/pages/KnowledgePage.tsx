import type { KnowledgeDocument, KnowledgeMatch, KnowledgeStatus } from "../types";
import type { DataColumn } from "../ui";
import { PageHeader } from "../components/PageHeader";
import { KnowledgeDocumentsPanel } from "./knowledge/KnowledgeDocumentsPanel";
import { KnowledgeSearchPanel } from "./knowledge/KnowledgeSearchPanel";
import { KnowledgeStatusPanel } from "./knowledge/KnowledgeStatusPanel";
import { KnowledgeUploadPanel } from "./knowledge/KnowledgeUploadPanel";

type Props = {
  knowledgeColumns: DataColumn<KnowledgeDocument>[];
  knowledgeDocuments: KnowledgeDocument[];
  knowledgeFiles: File[];
  knowledgeMatches: KnowledgeMatch[];
  knowledgeStatus?: KnowledgeStatus;
  loading: boolean;
  selectedProjectId?: string;
  onSearchKnowledge: (values: { query: string; project_id?: string; limit?: string }) => void;
  onSetKnowledgeFiles: (files: File[]) => void;
  onUploadKnowledgeDocument: (values: { title: string; scope?: string; project_id?: string }) => void;
};

export function KnowledgePage({
  knowledgeColumns,
  knowledgeDocuments,
  knowledgeFiles,
  knowledgeMatches,
  knowledgeStatus,
  loading,
  selectedProjectId,
  onSearchKnowledge,
  onSetKnowledgeFiles,
  onUploadKnowledgeDocument,
}: Props) {
  return (
    <>
      <PageHeader title="Knowledge" eyebrow="Prepare" />
      <div className="grid gap-4 xl:grid-cols-[minmax(420px,0.9fr)_minmax(480px,1.1fr)]">
        <div className="grid gap-4">
          <KnowledgeStatusPanel documents={knowledgeDocuments} status={knowledgeStatus} />
          <KnowledgeUploadPanel
            files={knowledgeFiles}
            loading={loading}
            selectedProjectId={selectedProjectId}
            onSetFiles={onSetKnowledgeFiles}
            onUpload={onUploadKnowledgeDocument}
          />
          <KnowledgeDocumentsPanel columns={knowledgeColumns} documents={knowledgeDocuments} />
        </div>
        <KnowledgeSearchPanel loading={loading} matches={knowledgeMatches} selectedProjectId={selectedProjectId} onSearch={onSearchKnowledge} />
      </div>
    </>
  );
}

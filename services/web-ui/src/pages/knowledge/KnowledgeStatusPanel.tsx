import type { KnowledgeDocument, KnowledgeStatus } from "../../types";
import { Badge, Panel } from "../../ui";
import { statusTone } from "../../utils/format";

type Props = {
  documents: KnowledgeDocument[];
  status?: KnowledgeStatus;
};

export function KnowledgeStatusPanel({ documents, status }: Props) {
  const indexedChunks = documents.reduce((total, item) => total + (item.chunk_count || 0), 0);
  const documentCount = status?.documents?.document_count ?? documents.length;
  const chunkCount = status?.documents?.chunk_count ?? indexedChunks;

  return (
    <Panel title="Readiness">
      <dl className="grid gap-3 text-sm">
        <InfoRow label="Embedding" value={<span className="inline-flex items-center gap-2"><Badge tone={statusTone(status?.embedding?.status)}>{status?.embedding?.status || "unknown"}</Badge>{status?.embedding?.provider || "-"}</span>} />
        <InfoRow label="Embedding Detail" value={status?.embedding?.message || "-"} />
        <InfoRow label="Collection" value={<span className="inline-flex items-center gap-2"><Badge tone={statusTone(status?.vector_store?.status)}>{status?.vector_store?.status || "unknown"}</Badge>{status?.vector_store?.collection || status?.embedding?.collection || "-"}</span>} />
        <InfoRow label="Vector Detail" value={status?.vector_store?.message || "-"} />
        <InfoRow label="Documents" value={documentCount} />
        <InfoRow label="Chunks" value={chunkCount} />
      </dl>
    </Panel>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid gap-1">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="text-slate-800">{value}</dd>
    </div>
  );
}

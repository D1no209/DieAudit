import { Card, Descriptions, Tag } from "antd";
import type { KnowledgeDocument, KnowledgeStatus } from "../../types";

type Props = {
  documents: KnowledgeDocument[];
  status?: KnowledgeStatus;
};

function statusColor(value?: string) {
  if (value === "pass") return "green";
  if (value === "warn") return "gold";
  if (value === "fail") return "red";
  return "default";
}

export function KnowledgeStatusPanel({ documents, status }: Props) {
  const indexedChunks = documents.reduce((total, item) => total + (item.chunk_count || 0), 0);
  const documentCount = status?.documents?.document_count ?? documents.length;
  const chunkCount = status?.documents?.chunk_count ?? indexedChunks;

  return (
    <Card title="Readiness">
      <Descriptions column={1} size="small">
        <Descriptions.Item label="Embedding">
          <Tag color={statusColor(status?.embedding?.status)}>{status?.embedding?.status || "unknown"}</Tag>
          {status?.embedding?.provider || "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Embedding Detail">{status?.embedding?.message || "-"}</Descriptions.Item>
        <Descriptions.Item label="Collection">
          <Tag color={statusColor(status?.vector_store?.status)}>{status?.vector_store?.status || "unknown"}</Tag>
          {status?.vector_store?.collection || status?.embedding?.collection || "-"}
        </Descriptions.Item>
        <Descriptions.Item label="Vector Detail">{status?.vector_store?.message || "-"}</Descriptions.Item>
        <Descriptions.Item label="Documents">{documentCount}</Descriptions.Item>
        <Descriptions.Item label="Chunks">{chunkCount}</Descriptions.Item>
      </Descriptions>
    </Card>
  );
}

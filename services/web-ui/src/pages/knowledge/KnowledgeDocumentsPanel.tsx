import { Card, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { KnowledgeDocument } from "../../types";

type Props = {
  columns: ColumnsType<KnowledgeDocument>;
  documents: KnowledgeDocument[];
};

export function KnowledgeDocumentsPanel({ columns, documents }: Props) {
  return (
    <Card title="Indexed Documents">
      <Table rowKey="document_id" columns={columns} dataSource={documents} pagination={{ pageSize: 6 }} />
    </Card>
  );
}

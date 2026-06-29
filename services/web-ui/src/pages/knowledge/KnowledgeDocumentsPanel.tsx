import type { KnowledgeDocument } from "../../types";
import { DataTable, Panel, type DataColumn } from "../../ui";

type Props = {
  columns: DataColumn<KnowledgeDocument>[];
  documents: KnowledgeDocument[];
};

export function KnowledgeDocumentsPanel({ columns, documents }: Props) {
  return (
    <Panel title="Indexed Documents">
      <DataTable getRowKey={(row) => row.document_id} columns={columns} data={documents} pagination={{ pageSize: 6 }} />
    </Panel>
  );
}

import type { KnowledgeMatch } from "../../types";
import { Badge, Button, Field, Input, Panel, fieldValue } from "../../ui";

type Props = {
  loading: boolean;
  matches: KnowledgeMatch[];
  selectedProjectId?: string;
  onSearch: (values: { query: string; project_id?: string; limit?: string }) => void;
};

export function KnowledgeSearchPanel({ loading, matches, selectedProjectId, onSearch }: Props) {
  return (
    <Panel title="Search">
      <form
        className="mb-4 grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          const formData = new FormData(event.currentTarget);
          onSearch({
            query: fieldValue(formData, "query") || "",
            project_id: fieldValue(formData, "project_id"),
            limit: fieldValue(formData, "limit"),
          });
        }}
      >
        <Field label="Query"><Input name="query" required /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Project Filter"><Input name="project_id" placeholder={selectedProjectId || "optional"} /></Field>
          <Field label="Limit"><Input name="limit" defaultValue="8" /></Field>
        </div>
        <Button type="submit" variant="primary" loading={loading}>检索</Button>
      </form>
      <div className="grid gap-3">
        {matches.map((item) => (
          <article key={`${item.document_id}-${item.chunk_id}`} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <h3 className="font-medium text-slate-900">{item.title || item.source_name}</h3>
            <div className="mt-2 flex flex-wrap gap-1">
              <Badge>{Number(item.score || 0).toFixed(3)}</Badge>
              <Badge>{item.scope}</Badge>
              <Badge>{item.document_id}</Badge>
              <Badge>{item.chunk_id}</Badge>
              {item.evidence?.kind ? <Badge tone="processing">{item.evidence.kind}</Badge> : null}
            </div>
            <p className="mt-3 line-clamp-4 text-sm leading-6 text-slate-600">{item.text}</p>
          </article>
        ))}
      </div>
    </Panel>
  );
}

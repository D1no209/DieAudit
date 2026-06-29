import type { ApiKeyRecord } from "../../types";
import { Alert, Button, DataTable, Field, Input, Panel, fieldValue, type DataColumn } from "../../ui";

type Props = {
  apiKeyColumns: DataColumn<ApiKeyRecord>[];
  apiKeys: ApiKeyRecord[];
  loading: boolean;
  onCreateManagedApiKey: (values: { name: string; scopes?: string; project_ids?: string; audit_run_ids?: string }) => void;
};

export function ApiKeysPanel({ apiKeyColumns, apiKeys, loading, onCreateManagedApiKey }: Props) {
  return (
    <Panel>
      <form
        className="mb-4 grid gap-3 lg:grid-cols-[minmax(180px,1fr)_minmax(200px,1fr)_minmax(180px,1fr)_minmax(180px,1fr)_auto]"
        onSubmit={(event) => {
          event.preventDefault();
          const formData = new FormData(event.currentTarget);
          onCreateManagedApiKey({
            name: fieldValue(formData, "name") || "",
            scopes: fieldValue(formData, "scopes"),
            project_ids: fieldValue(formData, "project_ids"),
            audit_run_ids: fieldValue(formData, "audit_run_ids"),
          });
          event.currentTarget.reset();
        }}
      >
        <Field label="Key name"><Input name="name" required placeholder="Key name" /></Field>
        <Field label="Scopes"><Input name="scopes" defaultValue="admin" placeholder="Scopes: admin,audit,runtime" /></Field>
        <Field label="Project IDs"><Input name="project_ids" placeholder="Project IDs (optional)" /></Field>
        <Field label="AuditRun IDs"><Input name="audit_run_ids" placeholder="AuditRun IDs (optional)" /></Field>
        <div className="flex items-end"><Button type="submit" variant="primary" loading={loading}>创建 Key</Button></div>
      </form>
      <Alert className="mb-4" tone="processing" title="新 Key 原文只在创建响应中显示一次；数据库只保存哈希。" />
      <DataTable getRowKey={(row) => row.key_id} columns={apiKeyColumns} data={apiKeys} pagination={{ pageSize: 8 }} />
    </Panel>
  );
}

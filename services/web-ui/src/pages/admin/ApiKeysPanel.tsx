import { Alert, Button, Card, Form, Input, Table } from "antd";
import type { FormInstance } from "antd/es/form";
import type { ColumnsType } from "antd/es/table";
import type { ApiKeyRecord } from "../../types";

type Props = {
  apiKeyColumns: ColumnsType<ApiKeyRecord>;
  apiKeyForm: FormInstance;
  apiKeys: ApiKeyRecord[];
  loading: boolean;
  onCreateManagedApiKey: (values: { name: string; scopes?: string; project_ids?: string; audit_run_ids?: string }) => void;
};

export function ApiKeysPanel({ apiKeyColumns, apiKeyForm, apiKeys, loading, onCreateManagedApiKey }: Props) {
  return (
    <Card>
      <Form form={apiKeyForm} layout="inline" onFinish={onCreateManagedApiKey} className="table-toolbar">
        <Form.Item name="name" rules={[{ required: true }]} className="api-key-name-field">
          <Input placeholder="Key name" />
        </Form.Item>
        <Form.Item name="scopes" initialValue="admin">
          <Input placeholder="Scopes: admin,audit,runtime" />
        </Form.Item>
        <Form.Item name="project_ids">
          <Input placeholder="Project IDs (optional)" />
        </Form.Item>
        <Form.Item name="audit_run_ids">
          <Input placeholder="AuditRun IDs (optional)" />
        </Form.Item>
        <Button htmlType="submit" type="primary" loading={loading}>
          创建 Key
        </Button>
      </Form>
      <Alert type="info" showIcon className="table-toolbar" message="新 Key 原文只在创建响应中显示一次；数据库只保存哈希。" />
      <Table rowKey="key_id" columns={apiKeyColumns} dataSource={apiKeys} pagination={{ pageSize: 8 }} />
    </Card>
  );
}

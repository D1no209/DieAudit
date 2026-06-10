import { DeleteOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Form, Input, Space, Table, Tabs, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { FormInstance } from "antd/es/form";
import type { ApiKeyRecord, PlatformAuditEvent, RuntimePolicy, StorageSummary } from "../types";
import { formatBytes, totalStorageBytes } from "../utils/format";

type Props = {
  apiKeyColumns: ColumnsType<ApiKeyRecord>;
  apiKeyForm: FormInstance;
  apiKeys: ApiKeyRecord[];
  loading: boolean;
  platformAuditColumns: ColumnsType<PlatformAuditEvent>;
  platformAuditEvents: PlatformAuditEvent[];
  runtimePolicy?: RuntimePolicy;
  storageSummary?: StorageSummary;
  onCleanupPlatformAuditEvents: () => void;
  onCreateManagedApiKey: (values: { name: string; scopes?: string }) => void;
  onPreviewLocalStorageCleanup: () => void;
};

export function AdminPage({
  apiKeyColumns,
  apiKeyForm,
  apiKeys,
  loading,
  platformAuditColumns,
  platformAuditEvents,
  runtimePolicy,
  storageSummary,
  onCleanupPlatformAuditEvents,
  onCreateManagedApiKey,
  onPreviewLocalStorageCleanup,
}: Props) {
  return (
    <Tabs
      className="section"
      items={[
        {
          key: "platform-audit",
          label: "Platform Audit",
          children: (
            <Card>
              <Space wrap className="table-toolbar">
                <Tag>retention: {runtimePolicy?.platform_audit_events?.retention_days ?? "-"}d</Tag>
                <Tag>max rows: {runtimePolicy?.platform_audit_events?.max_rows ?? "-"}</Tag>
                <Tag>runtime pkg: {runtimePolicy?.local_storage?.runtime_package_retention_days ?? "-"}d</Tag>
                <Tag>upload staging: {runtimePolicy?.local_storage?.upload_staging_retention_days ?? "-"}d</Tag>
                <Tag>unref workspaces: {runtimePolicy?.local_storage?.unreferenced_workspace_retention_days ?? "-"}d</Tag>
                <Tag>unref snapshots: {runtimePolicy?.local_storage?.unreferenced_snapshot_retention_days ?? "-"}d</Tag>
                <Tag>storage: {formatBytes(totalStorageBytes(storageSummary))}</Tag>
                <Tag>container memory: {runtimePolicy?.default_container?.memory ?? "-"}</Tag>
                <Tag>cpus: {runtimePolicy?.default_container?.cpus ?? "-"}</Tag>
                <Tag>max body: {formatBytes(runtimePolicy?.http_guards?.max_request_body_bytes)}</Tag>
                <Tag>max upload: {formatBytes(runtimePolicy?.http_guards?.max_upload_bytes)}</Tag>
                <Tag>zip files: {runtimePolicy?.workspace_import?.max_workspace_files ?? "-"}</Tag>
                <Tag>zip size: {formatBytes(runtimePolicy?.workspace_import?.max_workspace_uncompressed_bytes)}</Tag>
                <Tag>git schemes: {(runtimePolicy?.workspace_import?.allowed_git_url_schemes || []).join(",") || "-"}</Tag>
                <Tag>rate: {runtimePolicy?.http_guards?.rate_limit_per_minute ?? "-"} / {runtimePolicy?.http_guards?.rate_limit_window_seconds ?? "-"}s</Tag>
                <Button size="small" icon={<DeleteOutlined />} loading={loading} onClick={onCleanupPlatformAuditEvents}>
                  清理审计事件
                </Button>
                <Button size="small" icon={<DeleteOutlined />} loading={loading} onClick={onPreviewLocalStorageCleanup}>
                  预览存储清理
                </Button>
              </Space>
              <Table
                rowKey="id"
                columns={platformAuditColumns}
                dataSource={platformAuditEvents}
                pagination={{ pageSize: 10 }}
                scroll={{ x: 1200 }}
              />
            </Card>
          ),
        },
        {
          key: "api-keys",
          label: "API Keys",
          children: (
            <Card>
              <Form form={apiKeyForm} layout="inline" onFinish={onCreateManagedApiKey} className="table-toolbar">
                <Form.Item name="name" rules={[{ required: true }]} className="api-key-name-field">
                  <Input placeholder="Key name" />
                </Form.Item>
                <Form.Item name="scopes" initialValue="admin">
                  <Input placeholder="Scopes: admin,audit,runtime" />
                </Form.Item>
                <Button htmlType="submit" type="primary" loading={loading}>创建 Key</Button>
              </Form>
              <Alert
                type="info"
                showIcon
                className="table-toolbar"
                message="新 Key 原文只在创建响应中显示一次；数据库只保存哈希。"
              />
              <Table rowKey="key_id" columns={apiKeyColumns} dataSource={apiKeys} pagination={{ pageSize: 8 }} />
            </Card>
          ),
        },
      ]}
    />
  );
}

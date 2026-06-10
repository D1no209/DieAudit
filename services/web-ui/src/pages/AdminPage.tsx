import { Tabs } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { FormInstance } from "antd/es/form";
import type { ApiKeyRecord, PlatformAuditEvent, RuntimePolicy, StorageSummary } from "../types";
import { PageHeader } from "../components/PageHeader";
import { ApiKeysPanel } from "./admin/ApiKeysPanel";
import { PlatformAuditPanel } from "./admin/PlatformAuditPanel";

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
  onCreateManagedApiKey: (values: { name: string; scopes?: string; project_ids?: string; audit_run_ids?: string }) => void;
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
    <>
      <PageHeader title="Admin" />
      <Tabs
        className="section"
        items={[
          {
            key: "platform-audit",
            label: "Platform Audit",
            children: (
              <PlatformAuditPanel
                loading={loading}
                platformAuditColumns={platformAuditColumns}
                platformAuditEvents={platformAuditEvents}
                runtimePolicy={runtimePolicy}
                storageSummary={storageSummary}
                onCleanupPlatformAuditEvents={onCleanupPlatformAuditEvents}
                onPreviewLocalStorageCleanup={onPreviewLocalStorageCleanup}
              />
            ),
          },
          {
            key: "api-keys",
            label: "API Keys",
            children: (
              <ApiKeysPanel
                apiKeyColumns={apiKeyColumns}
                apiKeyForm={apiKeyForm}
                apiKeys={apiKeys}
                loading={loading}
                onCreateManagedApiKey={onCreateManagedApiKey}
              />
            ),
          },
        ]}
      />
    </>
  );
}

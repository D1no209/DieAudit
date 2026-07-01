import type { AgentModelConfig, AgentRuntimeAdapter, ApiKeyRecord, PlatformAuditEvent, RuntimePolicy, StorageSummary } from "../types";
import { PageHeader } from "../components/PageHeader";
import { Tabs, type DataColumn } from "../ui";
import { ApiKeysPanel } from "./admin/ApiKeysPanel";
import { AgentModelsPanel } from "./admin/AgentModelsPanel";
import { PlatformAuditPanel } from "./admin/PlatformAuditPanel";

type Props = {
  agentModelConfig?: AgentModelConfig;
  agentRuntimes: AgentRuntimeAdapter[];
  apiKeyColumns: DataColumn<ApiKeyRecord>[];
  apiKeys: ApiKeyRecord[];
  loading: boolean;
  platformAuditColumns: DataColumn<PlatformAuditEvent>[];
  platformAuditEvents: PlatformAuditEvent[];
  runtimePolicy?: RuntimePolicy;
  storageSummary?: StorageSummary;
  onCleanupPlatformAuditEvents: () => void;
  onCreateManagedApiKey: (values: { name: string; scopes?: string; project_ids?: string; audit_run_ids?: string }) => void;
  onPreviewLocalStorageCleanup: () => void;
  onUpdateAgentModelConfig: (values: AgentModelConfig) => void;
};

export function AdminPage({
  agentModelConfig,
  agentRuntimes,
  apiKeyColumns,
  apiKeys,
  loading,
  platformAuditColumns,
  platformAuditEvents,
  runtimePolicy,
  storageSummary,
  onCleanupPlatformAuditEvents,
  onCreateManagedApiKey,
  onPreviewLocalStorageCleanup,
  onUpdateAgentModelConfig,
}: Props) {
  return (
    <>
      <PageHeader title="Admin" eyebrow="Runtime/Admin" />
      <Tabs
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
            key: "agent-models",
            label: "Agent Models",
            children: (
              <AgentModelsPanel
                agentModelConfig={agentModelConfig}
                agentRuntimes={agentRuntimes}
                loading={loading}
                onSave={onUpdateAgentModelConfig}
              />
            ),
          },
          {
            key: "api-keys",
            label: "API Keys",
            children: (
              <ApiKeysPanel
                apiKeyColumns={apiKeyColumns}
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

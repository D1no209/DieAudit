import { bffGet, bffPost } from "./bffClient";

export type BffAuditRun = {
  audit_run_id: string;
  project_id: string;
  snapshot_id?: string;
  status: string;
  pipeline_status: string;
  current_stage?: string;
  cancel_requested: boolean;
  config: Record<string, unknown>;
  input_payload: Record<string, unknown>;
};

export type CreateAuditRunPayload = {
  project_id: string;
  snapshot_id?: string;
  enabled_agents?: string[];
  allow_external_network?: boolean;
  retain_runtime_on_failure?: boolean;
  input_payload?: Record<string, unknown>;
  config?: Record<string, unknown>;
};

export const auditRunsApi = {
  list: () => bffGet<BffAuditRun[]>("/audit-runs"),
  create: (payload: CreateAuditRunPayload) => bffPost<BffAuditRun>("/audit-runs", payload),
  get: (auditRunId: string) => bffGet<BffAuditRun>(`/audit-runs/${auditRunId}`),
  start: (auditRunId: string) => bffPost<{ queued: boolean; audit_run: BffAuditRun }>(`/audit-runs/${auditRunId}/start`),
  cancel: (auditRunId: string, reason: string) =>
    bffPost<{ cancel_requested: boolean; audit_run: BffAuditRun }>(`/audit-runs/${auditRunId}/cancel`, { reason }),
  graph: (auditRunId: string) => bffGet<Record<string, unknown>>(`/audit-runs/${auditRunId}/graph`),
};

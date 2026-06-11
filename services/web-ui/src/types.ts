export type Project = {
  project_id: string;
  name: string;
  source_type: string;
  source_uri?: string;
  default_branch?: string;
  status: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type ProjectSnapshot = {
  snapshot_id: string;
  project_id: string;
  source_type: string;
  source_ref?: string;
  workspace_path?: string;
  artifact_path?: string;
  artifact?: ArtifactRef;
  content_hash?: string;
  status?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type AuditRun = {
  audit_run_id: string;
  project_id: string;
  snapshot_id?: string;
  status: string;
  validator_rounds?: number;
  max_parallel_validators?: number;
  allow_external_network?: boolean;
  retain_runtime_on_failure?: boolean;
  config?: Record<string, unknown>;
  created_at: string;
  updated_at?: string;
};

export type AgentRun = {
  agent_run_id: string;
  audit_run_id?: string;
  project_id?: string;
  agent_name: string;
  template_name?: string;
  status: string;
  protocol_kind: string;
  input_summary?: Record<string, unknown>;
  output_summary?: Record<string, unknown>;
  artifact_path?: string;
  error?: string;
  created_at: string;
  updated_at?: string;
};

export type Finding = {
  finding_id: string;
  audit_run_id?: string;
  project_id?: string;
  title: string;
  severity: string;
  status: string;
  file_path?: string;
  line_start?: number;
  line_end?: number;
  rule_id?: string;
  source: string;
  description?: string;
  raw?: Record<string, unknown>;
  finding_markdown?: ArtifactRef & { exists?: boolean; artifact_id?: string; artifact_uri?: string };
  created_at?: string;
  updated_at?: string;
};

export type DependencyRecord = {
  dependency_id: string;
  audit_run_id: string;
  project_id: string;
  ecosystem: string;
  name: string;
  version?: string;
  manifest?: string;
  vulnerability_count: number;
  vulnerabilities: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
};

export type DependencySummary = {
  total: number;
  vulnerable: number;
  by_ecosystem: Record<string, number>;
};

export type DependencyInventory = {
  audit_run_id: string;
  packages: DependencyRecord[];
  summary: DependencySummary;
};

export type CodeAnalysisTask = {
  task_id: string;
  audit_run_id: string;
  project_id: string;
  title: string;
  focus: string;
  file_paths: string[];
  status: string;
  agent_run_id?: string;
  result?: Record<string, unknown>;
  created_at: string;
  updated_at?: string;
};

export type ArtifactRef = {
  artifact_id?: string;
  artifact_uri?: string;
  path: string;
  relative_path: string;
  name: string;
  size?: number;
  download_url: string;
  canonical_download_url?: string;
};

export type EvidenceRow = {
  evidence_id: string;
  finding_id?: string;
  audit_run_id?: string;
  kind: string;
  summary?: string;
  artifact_path?: string;
  artifact?: ArtifactRef;
  payload?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type FindingDetail = {
  finding: Finding;
  evidence: EvidenceRow[];
  validation_attempts: ValidationAttempt[];
};

export type ValidationAttempt = {
  attempt_id: string;
  finding_id: string;
  audit_run_id: string;
  agent_run_id?: string;
  round_index: number;
  status: string;
  result?: Record<string, unknown>;
  created_at: string;
  updated_at?: string;
};

export type ReportArtifact = {
  report_id: string;
  audit_run_id?: string;
  project_id?: string;
  kind: string;
  path: string;
  artifact?: ArtifactRef;
  summary: Record<string, unknown>;
  created_at: string;
  updated_at?: string;
};

export type AuditRunEvent = {
  id: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AgentRunEvent = {
  id: number;
  agent_run_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type PipelineStatus = {
  audit_run?: AuditRun;
  pipeline?: Record<string, unknown>;
  current?: {
    stage?: string;
    status?: string;
    error?: string;
  };
  runtime_control?: {
    cancel_requested?: boolean;
    cancel_reason?: string;
    cancel_requested_at?: string;
  };
  counts?: {
    findings?: Record<string, number>;
    validation_attempts?: Record<string, number>;
    reports?: number;
  };
  events: AuditRunEvent[];
};

export type ManagedRuntime = {
  summary?: {
    container_count?: number;
    network_count?: number;
    run_count?: number;
    expired_run_count?: number;
  };
};

export type DockerHealth = {
  ok?: boolean;
  status?: string;
  [key: string]: unknown;
};

export type RuntimePolicy = {
  default_container?: {
    memory?: string;
    cpus?: number;
    pids_limit?: number;
    tmpfs?: string;
  };
  platform_audit_events?: {
    retention_days?: number;
    max_rows?: number;
  };
  local_storage?: {
    runtime_package_retention_days?: number;
    upload_staging_retention_days?: number;
    unreferenced_workspace_retention_days?: number;
    unreferenced_snapshot_retention_days?: number;
    cleanup_max_entries?: number;
  };
  http_guards?: {
    max_request_body_bytes?: number;
    max_upload_bytes?: number;
    rate_limit_per_minute?: number;
    rate_limit_window_seconds?: number;
  };
  workspace_import?: {
    max_workspace_files?: number;
    max_workspace_uncompressed_bytes?: number;
    allowed_git_url_schemes?: string[];
    allowed_git_hosts?: string[];
  };
  pipeline?: {
    execution_backend?: string;
    recovery_on_startup?: boolean;
  };
  sandbox?: {
    default_runtime?: string;
    enable_gvisor?: boolean;
    allow_runc_sandbox?: boolean;
  };
};

export type StorageSummary = {
  roots?: Record<string, { path: string; exists: boolean; files: number; dirs: number; bytes: number }>;
  managed_prefixes?: Record<string, { path: string; exists: boolean; files: number; dirs: number; bytes: number }>;
  policy?: Record<string, number>;
};

export type RuntimeReadiness = {
  ok?: boolean;
  status?: string;
  summary?: {
    fail?: number;
    warn?: number;
    pass?: number;
  };
  checks?: RuntimeReadinessCheck[];
  blocking_checks?: RuntimeReadinessCheck[];
  warning_checks?: RuntimeReadinessCheck[];
  next_actions?: Array<{
    id?: string;
    title?: string;
    status?: "pass" | "warn" | "fail";
    remediation?: string[];
  }>;
};

export type RuntimeReadinessCheck = {
    id: string;
    title: string;
    status: "pass" | "warn" | "fail";
    detail?: unknown;
    remediation?: string[];
};

export type WorkerHeartbeat = {
  worker_id: string;
  service_name: string;
  hostname: string;
  status: string;
  last_seen_at: string;
  age_seconds?: number;
  current_audit_run_id?: string;
  metadata?: Record<string, unknown>;
};

export type SandboxCapabilities = {
  ok?: boolean;
  docker_available?: boolean;
  configured_gvisor?: boolean;
  allow_runc_sandbox?: boolean;
  gvisor_available?: boolean;
  strong_isolation_available?: boolean;
  sandbox_execution_available?: boolean;
  requested_runtime?: string;
  reason?: string;
  warnings?: string[];
};

export type AuthStatus = {
  enabled?: boolean;
  bootstrap_key_enabled?: boolean;
  api_key_header?: string;
  public_metrics?: boolean;
  service?: string;
};

export type ApiHealth = {
  ok?: boolean;
  service?: string;
  [key: string]: unknown;
};

export type ApiKeyRecord = {
  key_id: string;
  name: string;
  scopes: string[];
  status: string;
  last_used_at?: string;
  deactivated_at?: string;
  metadata?: Record<string, unknown>;
  created_at: string;
};

export type PlatformAuditEvent = {
  id: number;
  service: string;
  method: string;
  path: string;
  status_code: number;
  client_host?: string;
  user_agent?: string;
  auth_enabled: boolean;
  auth_result: string;
  request_id?: string;
  metadata?: Record<string, unknown>;
  created_at: string;
};

export type KnowledgeDocument = {
  document_id: string;
  title: string;
  source_name: string;
  content_type?: string;
  scope: string;
  project_id?: string;
  status: string;
  chunk_count: number;
  created_at: string;
  updated_at?: string;
  artifact?: ArtifactRef;
  artifact_path?: string;
  metadata?: Record<string, unknown>;
};

export type KnowledgeMatch = {
  score?: number;
  document_id: string;
  chunk_id: string;
  title?: string;
  source_name?: string;
  scope?: string;
  project_id?: string;
  chunk_index?: number;
  text: string;
  metadata?: Record<string, unknown>;
  evidence?: {
    kind: string;
    summary?: string;
    payload: Record<string, unknown>;
  };
};

export type KnowledgeStatus = {
  embedding?: {
    provider?: string;
    collection?: string;
    vector_size?: number;
    semantic?: boolean;
    status?: "pass" | "warn" | "fail";
    message?: string;
    probe?: Record<string, unknown>;
  };
  vector_store?: {
    collection?: string;
    vector_size?: number;
    status?: "pass" | "warn" | "fail";
    message?: string;
    probe?: Record<string, unknown>;
  };
  documents?: {
    document_count?: number;
    chunk_count?: number;
  };
};

export type ContainerRow = {
  Id: string;
  Image: string;
  Names: string[];
  State: string;
  Status: string;
  Labels: Record<string, string>;
  role?: string;
  db_status?: string;
  exit_code?: number;
  log_artifact?: string;
  container_name?: string;
};

export type WorkerHeartbeatsResponse = {
  workers: WorkerHeartbeat[];
};

export type ProjectMutationResponse = {
  project: Project;
  snapshot?: ProjectSnapshot | Record<string, unknown> | null;
};

export type CreateAuditRunResponse = {
  audit_run: AuditRun;
  agent_run?: AgentRun | null;
};

export type KnowledgeSearchResponse = {
  query: string;
  matches: KnowledgeMatch[];
};

export type KnowledgeDocumentMutationResponse = {
  document?: KnowledgeDocument;
  chunks_indexed?: number;
  deleted?: boolean;
  deleted_artifact?: boolean;
  error?: string;
};

export type SandboxServiceResponse = {
  network: string;
  target_url: string;
  [key: string]: unknown;
};

export type FindingPocResponse = {
  finding: FindingDetail;
  [key: string]: unknown;
};

export type SandboxPocFormValues = {
  image: string;
  command: string;
  expected_exit_code?: number;
  mount_workspace?: boolean;
  retain_runtime_on_failure?: boolean;
  target_url?: string;
  timeout_seconds?: number;
};

export type SandboxServiceFormValues = {
  image: string;
  command: string;
  healthcheck_path?: string;
  mount_workspace?: boolean;
  port?: number;
  retain_runtime_on_failure?: boolean;
  service_name?: string;
  startup_timeout_seconds?: number;
};

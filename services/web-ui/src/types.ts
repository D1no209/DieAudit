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

export type WhiteboardAttachment = {
  attachment_id: string;
  card_id: string;
  path: string;
  label?: string;
  content_type?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
};

export type WhiteboardLinkCandidate = {
  title?: string;
  card_ids?: string[];
  status: "not_ready" | "finding" | "not_found" | "hint" | "impossible" | string;
  agent_run_id?: string;
  rationale?: string;
  metadata?: Record<string, unknown>;
};

export type WhiteboardCard = {
  card_id: string;
  title: string;
  card_type: string;
  status: string;
  author?: string;
  agent_run_id?: string;
  event_time?: string;
  content?: string;
  confidence?: string;
  finding_id?: string;
  file_path?: string;
  line_start?: number;
  line_end?: number;
  expected_predecessors?: WhiteboardLinkCandidate[];
  possible_successors?: WhiteboardLinkCandidate[];
  requirements?: string[];
  attachments?: WhiteboardAttachment[];
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type WhiteboardEdge = {
  edge_id: string;
  source_card_id: string;
  target_card_id: string;
  edge_type: string;
  rationale?: string;
  author?: string;
  agent_run_id?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
};

export type WhiteboardNote = {
  note_id: string;
  card_id?: string;
  author?: string;
  agent_run_id?: string;
  content: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
};

export type WhiteboardTask = {
  task_id: string;
  gap_card_id?: string;
  card_id?: string;
  agent_role: string;
  agent_name: string;
  status: string;
  round_index: number;
  attempt_index: number;
  agent_run_id?: string;
  parent_task_id?: string;
  root_task_id?: string;
  wait_reason?: string;
  wake_event_id?: string;
  task_group?: string;
  requested_by_agent_run_id?: string;
  prompt?: string;
  result?: Record<string, unknown>;
  created_at?: string;
};

export type WhiteboardEvent = {
  event_id: string;
  entity_type: string;
  entity_id: string;
  event_type: string;
  summary?: string;
  payload?: Record<string, unknown>;
  created_at?: string;
};

export type WhiteboardSubscription = {
  subscription_id: string;
  subscriber_task_id?: string;
  subscriber_agent_run_id?: string;
  filter?: Record<string, unknown>;
  cursor_event_id?: string;
  status: string;
  created_at?: string;
};

export type WhiteboardNotification = {
  notification_id: string;
  event_id: string;
  subscription_id: string;
  subscriber_task_id?: string;
  subscriber_agent_run_id?: string;
  status: string;
  claimed_by_agent_run_id?: string;
  lease_expires_at?: string;
  attempt_count?: number;
  summary?: string;
  payload?: Record<string, unknown>;
  created_at?: string;
};

export type WhiteboardScheduleRequest = {
  request_id: string;
  requested_by_task_id?: string;
  requested_by_agent_run_id?: string;
  suggested_agent_name?: string;
  goal: string;
  reason?: string;
  related_card_ids?: string[];
  status: string;
  decision?: Record<string, unknown>;
  task_id?: string;
  created_at?: string;
};

export type WhiteboardGraph = {
  audit_run_id: string;
  project_id: string;
  snapshot?: string;
  cards: WhiteboardCard[];
  edges: WhiteboardEdge[];
  notes: WhiteboardNote[];
  tasks: WhiteboardTask[];
  events?: WhiteboardEvent[];
  subscriptions?: WhiteboardSubscription[];
  notifications?: WhiteboardNotification[];
  schedule_requests?: WhiteboardScheduleRequest[];
  evidence: Array<{ evidence_id: string; finding_id?: string; summary?: string; artifact_path?: string; payload?: Record<string, unknown>; created_at?: string }>;
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

export type ExecutionGraphNode = {
  id: string;
  kind: string;
  label: string;
  status?: string;
  group?: string;
  target?: {
    view?: string;
    audit_run_id?: string;
    agent_run_id?: string;
    container_id?: string;
    card_id?: string;
    task_id?: string;
  };
  data?: Record<string, unknown>;
};

export type ExecutionGraphEdge = {
  source: string;
  target: string;
  type: string;
  data?: Record<string, unknown>;
};

export type ExecutionGraph = {
  audit_run_id: string;
  project_id: string;
  summary: {
    node_count?: number;
    by_kind?: Record<string, number>;
    by_status?: Record<string, number>;
    completed?: number;
    unfinished?: number;
    failed?: number;
  };
  nodes: ExecutionGraphNode[];
  edges: ExecutionGraphEdge[];
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

export type AuthPrincipal = {
  key_id?: string;
  name?: string;
  source?: string;
  scopes?: string[];
  [key: string]: unknown;
};

export type AuthMe = {
  access_token?: string;
  api_key_header?: string;
  authenticated: boolean;
  principal?: AuthPrincipal | null;
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
  container_id?: string;
  agent_run_id?: string;
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

export type CreateAuditRunPayload = {
  agent_name?: string;
  enabled_agents?: string[];
  preflight_prompt?: string;
  validator_rounds?: number;
  max_parallel_validators?: number;
  validator_agent_name?: string;
  enable_validation_judgement?: boolean;
  validation_judgement_agent_name?: string;
  enable_feedback_loop?: boolean;
  max_feedback_rounds?: number;
  enable_code_batch_analysis?: boolean;
  enable_batch_internal_semgrep?: boolean;
  enable_batch_internal_sca?: boolean;
  max_code_audit_tasks?: number;
  max_files_per_code_audit_task?: number;
  max_parallel_code_auditors?: number;
  code_auditor_agent_name?: string;
  enable_source_sink_analysis?: boolean;
  source_sink_finder_agent_name?: string;
  max_parallel_source_sink_finders?: number;
  max_source_sink_findings?: number;
  enable_validators?: boolean;
  enable_judgement?: boolean;
  judger_agent_name?: string;
  max_parallel_judgers?: number;
  enable_poc_writing?: boolean;
  poc_writer_agent_name?: string;
  max_parallel_poc_writers?: number;
  max_poc_findings?: number;
  enable_poc_verification?: boolean;
  poc_verifier_agent_name?: string;
  max_parallel_poc_verifiers?: number;
  enable_decompilation?: boolean;
  decompiled_source_dir?: string;
  decompile_max_artifact_size_mb?: number;
  decompile_timeout_seconds?: number;
  decompile_max_artifacts?: number;
  allow_external_network?: boolean;
  retain_runtime_on_failure?: boolean;
  input_payload?: Record<string, unknown>;
  start_agent?: boolean;
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

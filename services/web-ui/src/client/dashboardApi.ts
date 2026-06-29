import { formatHttpError, readJson, withAuth } from "../api";
import type {
  AgentRun,
  AgentRunEvent,
  ApiHealth,
  ApiKeyRecord,
  AuditRun,
  AuthStatus,
  CodeAnalysisTask,
  ContainerRow,
  CreateAuditRunPayload,
  CreateAuditRunResponse,
  DependencyInventory,
  DockerHealth,
  ExecutionGraph,
  Finding,
  FindingDetail,
  FindingPocResponse,
  KnowledgeDocument,
  KnowledgeDocumentMutationResponse,
  KnowledgeSearchResponse,
  KnowledgeStatus,
  ManagedRuntime,
  PipelineStatus,
  PlatformAuditEvent,
  Project,
  ProjectMutationResponse,
  ReportArtifact,
  RuntimePolicy,
  RuntimeReadiness,
  SandboxCapabilities,
  SandboxServiceResponse,
  StorageSummary,
  WhiteboardGraph,
  WorkerHeartbeatsResponse,
} from "../types";

type JsonObject = Record<string, unknown>;

const unsupportedSplitServiceAction = "当前 split-service 运行模式尚未实现此操作。";

function postJson<T = unknown>(path: string, body?: unknown) {
  return readJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function unsupported<T = JsonObject>(feature: string): Promise<T> {
  return Promise.reject(new Error(`${feature}: ${unsupportedSplitServiceAction}`));
}

export function getPlatformBootstrap() {
  return Promise.all([
    readJson<ApiHealth>("/api/health"),
    readJson<{ authenticated?: boolean; api_key_header?: string; service?: string }>("/api/bff/session").then((session) => ({
      enabled: false,
      api_key_header: session.api_key_header,
      service: session.service,
    })),
  ]);
}

export function getDockerHealth() {
  return readJson<DockerHealth>("/gateway/internal/runtime/docker/health").catch(() => ({ ok: false, status: "unavailable" }));
}

export function listProjects() {
  return readJson<Project[]>("/api/bff/projects");
}

export function getManagedRuntime() {
  return readJson<ManagedRuntime>("/api/bff/runtime/managed");
}

export function getStorageSummary() {
  return Promise.resolve<StorageSummary>({});
}

export function getRuntimePolicy() {
  return Promise.resolve<RuntimePolicy>({});
}

export function getRuntimeReadiness() {
  return readJson<RuntimeReadiness>("/api/bff/runtime/readiness").then((readiness) => ({
    ...readiness,
    summary: {
      fail: readiness.ok ? 0 : 1,
      warn: 0,
      pass: readiness.ok ? 1 : 0,
      ...readiness.summary,
    },
    blocking_checks: readiness.blocking_checks || [],
    warning_checks: readiness.warning_checks || [],
    next_actions: readiness.next_actions || [],
  }));
}

export function getWorkerHeartbeats() {
  return Promise.resolve<WorkerHeartbeatsResponse>({ workers: [] });
}

export function getSandboxCapabilities() {
  return Promise.resolve<SandboxCapabilities>({
    ok: false,
    sandbox_execution_available: false,
    reason: "当前 split-service BFF 尚未暴露 sandbox capabilities。",
    warnings: ["Sandbox actions are unavailable in this split-service skeleton."],
  });
}

export function listApiKeys() {
  return Promise.resolve<ApiKeyRecord[]>([]);
}

export function listPlatformAuditEvents() {
  return readJson<PlatformAuditEvent[]>("/api/bff/admin/audit-events");
}

export function listKnowledgeDocuments() {
  return readJson<KnowledgeDocument[]>("/api/bff/knowledge/documents");
}

export function getKnowledgeStatus() {
  return readJson<KnowledgeStatus>("/api/bff/knowledge/status");
}

export async function getAuditRunBundle(auditRunId: string) {
  const [run, executionGraph] = await Promise.all([
    readJson<AuditRun>(`/api/bff/audit-runs/${auditRunId}`),
    readJson<ExecutionGraph>(`/api/bff/audit-runs/${auditRunId}/graph`).catch(() => undefined),
  ]);
  return {
    agents: [] as AgentRun[],
    codeAnalysisTasks: [] as CodeAnalysisTask[],
    containers: [] as ContainerRow[],
    dependencies: undefined as DependencyInventory | undefined,
    executionGraph,
    findings: [] as Finding[],
    pipeline: { audit_run: run, events: [] } as PipelineStatus,
    reports: [] as ReportArtifact[],
    run,
    whiteboard: undefined as WhiteboardGraph | undefined,
  };
}

export function createGitProject(values: { name: string; git_url: string; ref?: string }) {
  return postJson<Project>("/api/bff/projects", values).then((project) => ({ project }));
}

export function uploadZipProject(formData: FormData) {
  const name = String(formData.get("name") || "Uploaded project");
  return postJson<Project>("/api/bff/projects", { name, metadata: { upload_zip_unavailable: true } }).then((project) => ({ project }));
}

export function createAuditRun(projectId: string, payload: CreateAuditRunPayload) {
  const config = { ...payload };
  return postJson<AuditRun>("/api/bff/audit-runs", {
    project_id: projectId,
    enabled_agents: payload.enabled_agents || [],
    allow_external_network: Boolean(payload.allow_external_network),
    retain_runtime_on_failure: Boolean(payload.retain_runtime_on_failure),
    input_payload: payload.input_payload || {},
    config,
  }).then((audit_run) => ({ audit_run }));
}

export function runSca(auditRunId: string) {
  return unsupported(`SCA (${auditRunId})`);
}

export function runCodeAnalysis(auditRunId: string) {
  return unsupported(`Code analysis (${auditRunId})`);
}

export function runPipeline(auditRunId: string) {
  return postJson<JsonObject>(`/api/bff/audit-runs/${auditRunId}/start`, { force: false });
}

export function runJudge(auditRunId: string) {
  return unsupported(`Judgement (${auditRunId})`);
}

export function runWhiteboardSwarm(auditRunId: string) {
  return unsupported(`Whiteboard swarm (${auditRunId})`);
}

export function generateReport(auditRunId: string) {
  return unsupported(`Report generation (${auditRunId})`);
}

export function runSandboxPoc(auditRunId: string, body: Record<string, unknown>) {
  return unsupported(`Sandbox PoC (${auditRunId})`);
}

export function startSandboxService(auditRunId: string, body: Record<string, unknown>) {
  return unsupported<SandboxServiceResponse>(`Sandbox service (${auditRunId})`);
}

export function getFinding(findingId: string) {
  return unsupported<FindingDetail>(`Finding detail (${findingId})`);
}

export function runFindingPoc(findingId: string, body: Record<string, unknown>) {
  return unsupported<FindingPocResponse>(`Finding PoC (${findingId})`);
}

export function getAgentEvents(auditRunId: string, agentRunId: string) {
  return Promise.resolve<AgentRunEvent[]>([]);
}

export function getContainerLogs(auditRunId: string, containerId: string) {
  return unsupported<string>(`Container logs (${auditRunId}/${containerId})`);
}

export function cleanupAuditRun(auditRunId: string) {
  return unsupported(`Runtime cleanup (${auditRunId})`);
}

export function cancelAuditRun(auditRunId: string) {
  return postJson<JsonObject>(`/api/bff/audit-runs/${auditRunId}/cancel`, { reason: "cancelled by user" });
}

export function cleanupExpiredRuntime() {
  return unsupported("Expired runtime cleanup");
}

export function previewLocalStorageCleanup() {
  return Promise.resolve<JsonObject>({ ok: true, dry_run: true, unavailable: true });
}

export function cleanupPlatformAuditEvents() {
  return unsupported("Platform audit event cleanup");
}

export function createManagedApiKey(body: Record<string, unknown>) {
  return unsupported<ApiKeyRecord>("API key creation");
}

export function deactivateManagedApiKey(keyId: string) {
  return unsupported<ApiKeyRecord>(`API key deactivation (${keyId})`);
}

export function uploadKnowledgeDocument(formData: FormData) {
  return unsupported<KnowledgeDocumentMutationResponse>("Knowledge upload");
}

export function searchKnowledge(body: Record<string, unknown>) {
  return Promise.resolve<KnowledgeSearchResponse>({ query: String(body.query || ""), matches: [] });
}

export function reindexKnowledgeDocument(documentId: string) {
  return unsupported<KnowledgeDocumentMutationResponse>(`Knowledge reindex (${documentId})`);
}

export function deleteKnowledgeDocument(documentId: string) {
  return unsupported<KnowledgeDocumentMutationResponse>(`Knowledge delete (${documentId})`);
}

export async function fetchArtifactBlob(url: string) {
  const response = await fetch(url, withAuth());
  const text = response.ok ? undefined : await response.text();
  if (!response.ok) {
    throw new Error(formatHttpError(text || "", response.statusText));
  }
  return response.blob();
}

import { formatHttpError, readJson, withAuth } from "../api";
import type {
  AgentRun,
  AgentRunEvent,
  AgentModelConfig,
  AgentRuntimeAdapter,
  AgentTranscriptEvent,
  ApiHealth,
  AuthMe,
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

function postJson<T = unknown>(path: string, body?: unknown) {
  return readJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function getPlatformBootstrap() {
  return Promise.all([readJson<ApiHealth>("/api/health"), readJson<AuthStatus>("/api/bff/session/status")]);
}

export async function loginWithPassword(username: string, password: string) {
  const response = await fetch("/api/bff/session/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(formatHttpError(text, response.statusText));
  }
  return (text ? JSON.parse(text) : {}) as AuthMe;
}

export function getCurrentAuthPrincipal() {
  return readJson<AuthMe>("/api/bff/session");
}

export function listAgentRuntimes() {
  return readJson<AgentRuntimeAdapter[]>("/api/bff/agent-runtimes");
}

export function getDockerHealth() {
  return readJson<DockerHealth>("/api/bff/runtime/docker/health");
}

export function listProjects() {
  return readJson<Project[]>("/api/bff/projects");
}

export function listProjectAuditRuns(projectId: string) {
  return readJson<AuditRun[]>("/api/bff/audit-runs").then((runs) => runs.filter((run) => run.project_id === projectId));
}

export function getAuditRun(auditRunId: string) {
  return readJson<AuditRun>(`/api/bff/audit-runs/${auditRunId}`);
}

export function getManagedRuntime() {
  return readJson<ManagedRuntime>("/api/bff/runtime/managed");
}

export function getStorageSummary() {
  return readJson<StorageSummary>("/api/bff/runtime/storage");
}

export function getRuntimePolicy() {
  return readJson<RuntimePolicy>("/api/bff/runtime/policy");
}

export function getRuntimeReadiness() {
  return readJson<RuntimeReadiness>("/api/bff/runtime/readiness");
}

export function getWorkerHeartbeats() {
  return readJson<WorkerHeartbeatsResponse>("/api/bff/runtime/workers");
}

export function getSandboxCapabilities() {
  return readJson<SandboxCapabilities>("/api/bff/runtime/sandbox/capabilities");
}

export function listApiKeys() {
  return readJson<ApiKeyRecord[]>("/api/bff/admin/api-keys");
}

export function listPlatformAuditEvents() {
  return readJson<PlatformAuditEvent[]>("/api/bff/admin/audit-events?limit=100");
}

export function getAgentModelConfig() {
  return readJson<AgentModelConfig>("/api/bff/admin/agent-model-config");
}

export function updateAgentModelConfig(body: AgentModelConfig) {
  return readJson<AgentModelConfig>("/api/bff/admin/agent-model-config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function listKnowledgeDocuments() {
  return readJson<KnowledgeDocument[]>("/api/bff/knowledge/documents");
}

export function getKnowledgeStatus() {
  return readJson<KnowledgeStatus>("/api/bff/knowledge/status");
}

export async function getAuditRunBundle(auditRunId: string) {
  const [run, agents, findings, codeAnalysisTasks, dependencies, containers, reports, pipeline, whiteboard, executionGraph] = await Promise.all([
    readJson<AuditRun>(`/api/bff/audit-runs/${auditRunId}`),
    readJson<AgentRun[]>(`/api/bff/audit-runs/${auditRunId}/agent-runs`),
    readJson<Finding[]>(`/api/bff/audit-runs/${auditRunId}/findings`),
    readJson<CodeAnalysisTask[]>(`/api/bff/audit-runs/${auditRunId}/code-analysis/tasks`).catch(() => []),
    readJson<DependencyInventory>(`/api/bff/audit-runs/${auditRunId}/dependencies`).catch(() => undefined),
    readJson<ContainerRow[]>(`/api/bff/audit-runs/${auditRunId}/containers`),
    readJson<ReportArtifact[]>(`/api/bff/audit-runs/${auditRunId}/reports`),
    readJson<PipelineStatus>(`/api/bff/audit-runs/${auditRunId}/pipeline-status`),
    readJson<WhiteboardGraph>(`/api/bff/audit-runs/${auditRunId}/whiteboard`).catch(() => undefined),
    readJson<ExecutionGraph>(`/api/bff/audit-runs/${auditRunId}/flow`).catch(() => undefined),
  ]);
  return { agents, codeAnalysisTasks, containers, dependencies, executionGraph, findings, pipeline, reports, run, whiteboard };
}

export function createGitProject(values: { name: string; git_url: string; ref?: string }) {
  return postJson<ProjectMutationResponse>("/api/bff/projects", values);
}

export function uploadZipProject(formData: FormData) {
  return readJson<ProjectMutationResponse>("/api/bff/projects/upload-zip", { method: "POST", body: formData });
}

export function createAuditRun(projectId: string, payload: CreateAuditRunPayload) {
  return postJson<CreateAuditRunResponse>("/api/bff/audit-runs", { project_id: projectId, ...payload });
}

export function runSca(auditRunId: string) {
  return postJson<JsonObject>(`/api/bff/audit-runs/${auditRunId}/start`, { force: true });
}

export function runCodeAnalysis(auditRunId: string) {
  return postJson<JsonObject>(`/api/bff/audit-runs/${auditRunId}/start`, { force: true });
}

export function runPipeline(auditRunId: string) {
  return postJson<JsonObject>(`/api/bff/audit-runs/${auditRunId}/start`, { force: true });
}

export function runJudge(auditRunId: string) {
  return postJson<JsonObject>(`/api/bff/audit-runs/${auditRunId}/start`, { force: true });
}

export function runWhiteboardSwarm(auditRunId: string) {
  return postJson<JsonObject>(`/api/bff/audit-runs/${auditRunId}/start`, { force: true });
}

export function generateReport(auditRunId: string) {
  return postJson<JsonObject>(`/api/bff/audit-runs/${auditRunId}/start`, { force: true });
}

export function runSandboxPoc(auditRunId: string, body: Record<string, unknown>) {
  return postJson<JsonObject>(`/api/bff/audit-runs/${auditRunId}/sandbox/poc`, body);
}

export function startSandboxService(auditRunId: string, body: Record<string, unknown>) {
  return postJson<SandboxServiceResponse>(`/api/bff/audit-runs/${auditRunId}/sandbox/service`, body);
}

export function getFinding(findingId: string) {
  return readJson<FindingDetail>(`/api/bff/findings/${findingId}`);
}

export function runFindingPoc(findingId: string, body: Record<string, unknown>) {
  return postJson<FindingPocResponse>(`/api/bff/findings/${findingId}/poc`, body);
}

export function getAgentEvents(auditRunId: string, agentRunId: string) {
  return readJson<AgentRunEvent[]>(`/api/bff/audit-runs/${auditRunId}/agent-runs/${agentRunId}/events`);
}

export function getAgentMessages(auditRunId: string, agentRunId: string) {
  return readJson<AgentTranscriptEvent[]>(`/api/bff/audit-runs/${auditRunId}/agent-runs/${agentRunId}/messages`);
}

export async function getContainerLogs(auditRunId: string, containerId: string) {
  const response = await fetch(
    `/api/bff/audit-runs/${auditRunId}/containers/${encodeURIComponent(containerId)}/logs`,
    withAuth(),
  );
  const text = await response.text();
  if (!response.ok) {
    throw new Error(formatHttpError(text, response.statusText));
  }
  return text;
}

export function cleanupAuditRun(auditRunId: string) {
  return postJson<JsonObject>(`/api/bff/audit-runs/${auditRunId}/cancel`, { reason: "cleanup requested" });
}

export function cancelAuditRun(auditRunId: string) {
  return postJson<JsonObject>(`/api/bff/audit-runs/${auditRunId}/cancel`, { reason: "user requested" });
}

export function cleanupExpiredRuntime() {
  return postJson<JsonObject>("/api/bff/runtime/cleanup-expired", {});
}

export function previewLocalStorageCleanup() {
  return postJson<JsonObject>("/api/bff/runtime/storage/cleanup", { dry_run: true });
}

export function cleanupPlatformAuditEvents() {
  return readJson<JsonObject>("/api/bff/admin/audit-events", { method: "DELETE" });
}

export function createManagedApiKey(body: Record<string, unknown>) {
  return postJson<ApiKeyRecord>("/api/bff/admin/api-keys", body);
}

export function deactivateManagedApiKey(keyId: string) {
  return readJson<ApiKeyRecord>(`/api/bff/admin/api-keys/${keyId}/deactivate`, { method: "POST" });
}

export function uploadKnowledgeDocument(formData: FormData) {
  return readJson<KnowledgeDocumentMutationResponse>("/api/bff/knowledge/documents", { method: "POST", body: formData });
}

export function searchKnowledge(body: Record<string, unknown>) {
  return postJson<KnowledgeSearchResponse>("/api/bff/knowledge/search", body);
}

export function reindexKnowledgeDocument(documentId: string) {
  return readJson<KnowledgeDocumentMutationResponse>(`/api/bff/knowledge/documents/${documentId}/reindex`, { method: "POST" });
}

export function deleteKnowledgeDocument(documentId: string) {
  return readJson<KnowledgeDocumentMutationResponse>(`/api/bff/knowledge/documents/${documentId}`, { method: "DELETE" });
}

export async function fetchArtifactBlob(url: string) {
  const response = await fetch(url, withAuth());
  const text = response.ok ? undefined : await response.text();
  if (!response.ok) {
    throw new Error(formatHttpError(text || "", response.statusText));
  }
  return response.blob();
}

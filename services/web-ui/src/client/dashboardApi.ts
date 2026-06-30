import { formatHttpError, readJson, withAuth } from "../api";
import type {
  AgentRun,
  AgentRunEvent,
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
  return Promise.all([readJson<ApiHealth>("/api/health"), readJson<AuthStatus>("/api/auth/status")]);
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

export function getDockerHealth() {
  return readJson<DockerHealth>("/gateway/runtime/docker/health");
}

export function listProjects() {
  return readJson<Project[]>("/gateway/projects");
}

export function listProjectAuditRuns(projectId: string) {
  return readJson<AuditRun[]>(`/gateway/projects/${projectId}/audit-runs`);
}

export function getManagedRuntime() {
  return readJson<ManagedRuntime>("/gateway/runtime/managed");
}

export function getStorageSummary() {
  return readJson<StorageSummary>("/gateway/runtime/storage");
}

export function getRuntimePolicy() {
  return readJson<RuntimePolicy>("/gateway/runtime/policy");
}

export function getRuntimeReadiness() {
  return readJson<RuntimeReadiness>("/gateway/runtime/readiness");
}

export function getWorkerHeartbeats() {
  return readJson<WorkerHeartbeatsResponse>("/gateway/runtime/workers");
}

export function getSandboxCapabilities() {
  return readJson<SandboxCapabilities>("/gateway/runtime/sandbox/capabilities");
}

export function listApiKeys() {
  return readJson<ApiKeyRecord[]>("/gateway/auth/api-keys");
}

export function listPlatformAuditEvents() {
  return readJson<PlatformAuditEvent[]>("/gateway/platform/audit-events?limit=100");
}

export function listKnowledgeDocuments() {
  return readJson<KnowledgeDocument[]>("/gateway/knowledge/documents");
}

export function getKnowledgeStatus() {
  return readJson<KnowledgeStatus>("/gateway/knowledge/status");
}

export async function getAuditRunBundle(auditRunId: string) {
  const [run, agents, findings, codeAnalysisTasks, dependencies, containers, reports, pipeline, whiteboard, executionGraph] = await Promise.all([
    readJson<AuditRun>(`/gateway/audit-runs/${auditRunId}`),
    readJson<AgentRun[]>(`/gateway/audit-runs/${auditRunId}/agent-runs`),
    readJson<Finding[]>(`/gateway/audit-runs/${auditRunId}/findings`),
    readJson<CodeAnalysisTask[]>(`/gateway/audit-runs/${auditRunId}/code-analysis/tasks`).catch(() => []),
    readJson<DependencyInventory>(`/gateway/audit-runs/${auditRunId}/dependencies`).catch(() => undefined),
    readJson<ContainerRow[]>(`/gateway/audit-runs/${auditRunId}/containers`),
    readJson<ReportArtifact[]>(`/gateway/audit-runs/${auditRunId}/reports`),
    readJson<PipelineStatus>(`/gateway/audit-runs/${auditRunId}/pipeline-status`),
    readJson<WhiteboardGraph>(`/gateway/audit-runs/${auditRunId}/whiteboard`).catch(() => undefined),
    readJson<ExecutionGraph>(`/gateway/audit-runs/${auditRunId}/execution-graph`).catch(() => undefined),
  ]);
  return { agents, codeAnalysisTasks, containers, dependencies, executionGraph, findings, pipeline, reports, run, whiteboard };
}

export function createGitProject(values: { name: string; git_url: string; ref?: string }) {
  return postJson<ProjectMutationResponse>("/gateway/projects", values);
}

export function uploadZipProject(formData: FormData) {
  return readJson<ProjectMutationResponse>("/gateway/projects/upload-zip", { method: "POST", body: formData });
}

export function createAuditRun(projectId: string, payload: CreateAuditRunPayload) {
  return postJson<CreateAuditRunResponse>(`/gateway/projects/${projectId}/audit-runs`, payload);
}

export function runSca(auditRunId: string) {
  return readJson<JsonObject>(`/gateway/audit-runs/${auditRunId}/sca`, { method: "POST" });
}

export function runCodeAnalysis(auditRunId: string) {
  return postJson<JsonObject>(`/gateway/audit-runs/${auditRunId}/code-analysis`, {
    max_tasks: 8,
    max_files_per_task: 25,
    max_parallel_agents: 2,
    agent_name: "kimi-code-auditor",
  });
}

export function runPipeline(auditRunId: string) {
  return readJson<JsonObject>(`/gateway/audit-runs/${auditRunId}/run-pipeline`, { method: "POST" });
}

export function runJudge(auditRunId: string) {
  return readJson<JsonObject>(`/gateway/audit-runs/${auditRunId}/judge`, { method: "POST" });
}

export function runWhiteboardSwarm(auditRunId: string) {
  return postJson<JsonObject>(`/gateway/audit-runs/${auditRunId}/whiteboard/tasks/run`, {});
}

export function generateReport(auditRunId: string) {
  return readJson<JsonObject>(`/gateway/audit-runs/${auditRunId}/report`, { method: "POST" });
}

export function runSandboxPoc(auditRunId: string, body: Record<string, unknown>) {
  return postJson<JsonObject>(`/gateway/audit-runs/${auditRunId}/sandbox/poc`, body);
}

export function startSandboxService(auditRunId: string, body: Record<string, unknown>) {
  return postJson<SandboxServiceResponse>(`/gateway/audit-runs/${auditRunId}/sandbox/service`, body);
}

export function getFinding(findingId: string) {
  return readJson<FindingDetail>(`/gateway/findings/${findingId}`);
}

export function runFindingPoc(findingId: string, body: Record<string, unknown>) {
  return postJson<FindingPocResponse>(`/gateway/findings/${findingId}/poc`, body);
}

export function getAgentEvents(auditRunId: string, agentRunId: string) {
  return readJson<AgentRunEvent[]>(`/gateway/audit-runs/${auditRunId}/agent-runs/${agentRunId}/events`);
}

export async function getContainerLogs(auditRunId: string, containerId: string) {
  const response = await fetch(
    `/gateway/audit-runs/${auditRunId}/containers/${encodeURIComponent(containerId)}/logs`,
    withAuth(),
  );
  const text = await response.text();
  if (!response.ok) {
    throw new Error(formatHttpError(text, response.statusText));
  }
  return text;
}

export function cleanupAuditRun(auditRunId: string) {
  return readJson<JsonObject>(`/gateway/audit-runs/${auditRunId}/cleanup`, { method: "POST" });
}

export function cancelAuditRun(auditRunId: string) {
  return readJson<JsonObject>(`/gateway/audit-runs/${auditRunId}/cancel`, { method: "POST" });
}

export function cleanupExpiredRuntime() {
  return readJson<JsonObject>("/gateway/runtime/cleanup-expired", { method: "POST" });
}

export function previewLocalStorageCleanup() {
  return postJson<JsonObject>("/gateway/runtime/storage/cleanup", { dry_run: true });
}

export function cleanupPlatformAuditEvents() {
  return readJson<JsonObject>("/gateway/platform/audit-events", { method: "DELETE" });
}

export function createManagedApiKey(body: Record<string, unknown>) {
  return postJson<ApiKeyRecord>("/gateway/auth/api-keys", body);
}

export function deactivateManagedApiKey(keyId: string) {
  return readJson<ApiKeyRecord>(`/gateway/auth/api-keys/${keyId}/deactivate`, { method: "POST" });
}

export function uploadKnowledgeDocument(formData: FormData) {
  return readJson<KnowledgeDocumentMutationResponse>("/gateway/knowledge/documents", { method: "POST", body: formData });
}

export function searchKnowledge(body: Record<string, unknown>) {
  return postJson<KnowledgeSearchResponse>("/gateway/knowledge/search", body);
}

export function reindexKnowledgeDocument(documentId: string) {
  return readJson<KnowledgeDocumentMutationResponse>(`/gateway/knowledge/documents/${documentId}/reindex`, { method: "POST" });
}

export function deleteKnowledgeDocument(documentId: string) {
  return readJson<KnowledgeDocumentMutationResponse>(`/gateway/knowledge/documents/${documentId}`, { method: "DELETE" });
}

export async function fetchArtifactBlob(url: string) {
  const response = await fetch(url, withAuth());
  const text = response.ok ? undefined : await response.text();
  if (!response.ok) {
    throw new Error(formatHttpError(text || "", response.statusText));
  }
  return response.blob();
}

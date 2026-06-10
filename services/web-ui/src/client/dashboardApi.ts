import { formatHttpError, readJson, withAuth } from "../api";

function postJson(path: string, body?: unknown) {
  return readJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function getPlatformBootstrap() {
  return Promise.all([readJson("/api/health"), readJson("/api/auth/status")]);
}

export function getDashboardProjects() {
  return Promise.all([readJson("/gateway/runtime/docker/health"), readJson("/gateway/projects")]);
}

export function getManagedRuntime() {
  return readJson("/gateway/runtime/managed");
}

export function getStorageSummary() {
  return readJson("/gateway/runtime/storage");
}

export function getRuntimePolicy() {
  return readJson("/gateway/runtime/policy");
}

export function getRuntimeReadiness() {
  return readJson("/gateway/runtime/readiness");
}

export function getWorkerHeartbeats() {
  return readJson("/gateway/runtime/workers");
}

export function getSandboxCapabilities() {
  return readJson("/gateway/runtime/sandbox/capabilities");
}

export function listApiKeys() {
  return readJson("/gateway/auth/api-keys");
}

export function listPlatformAuditEvents() {
  return readJson("/gateway/platform/audit-events?limit=100");
}

export function listKnowledgeDocuments() {
  return readJson("/gateway/knowledge/documents");
}

export async function getAuditRunBundle(auditRunId: string) {
  const [run, agents, findings, dependencies, containers, reports, pipeline] = await Promise.all([
    readJson(`/gateway/audit-runs/${auditRunId}`),
    readJson(`/gateway/audit-runs/${auditRunId}/agent-runs`),
    readJson(`/gateway/audit-runs/${auditRunId}/findings`),
    readJson(`/gateway/audit-runs/${auditRunId}/dependencies`).catch(() => undefined),
    readJson(`/gateway/audit-runs/${auditRunId}/containers`),
    readJson(`/gateway/audit-runs/${auditRunId}/reports`),
    readJson(`/gateway/audit-runs/${auditRunId}/pipeline-status`),
  ]);
  return { agents, containers, dependencies, findings, pipeline, reports, run };
}

export function createGitProject(values: { name: string; git_url: string; ref?: string }) {
  return postJson("/gateway/projects", values);
}

export function uploadZipProject(formData: FormData) {
  return readJson("/gateway/projects/upload-zip", { method: "POST", body: formData });
}

export function createAuditRun(projectId: string) {
  return postJson(`/gateway/projects/${projectId}/audit-runs`, {
    agent_name: "opencode-orchestrator",
    allow_external_network: false,
    input_payload: {
      goal: "Run an initial security audit. Inspect the mounted source and report vulnerability candidates with file paths.",
    },
  });
}

export function runSca(auditRunId: string) {
  return readJson(`/gateway/audit-runs/${auditRunId}/sca`, { method: "POST" });
}

export function runPipeline(auditRunId: string) {
  return readJson(`/gateway/audit-runs/${auditRunId}/run-pipeline`, { method: "POST" });
}

export function runJudge(auditRunId: string) {
  return readJson(`/gateway/audit-runs/${auditRunId}/judge`, { method: "POST" });
}

export function generateReport(auditRunId: string) {
  return readJson(`/gateway/audit-runs/${auditRunId}/report`, { method: "POST" });
}

export function runSandboxPoc(auditRunId: string, body: Record<string, unknown>) {
  return postJson(`/gateway/audit-runs/${auditRunId}/sandbox/poc`, body);
}

export function startSandboxService(auditRunId: string, body: Record<string, unknown>) {
  return postJson(`/gateway/audit-runs/${auditRunId}/sandbox/service`, body);
}

export function getFinding(findingId: string) {
  return readJson(`/gateway/findings/${findingId}`);
}

export function runFindingPoc(findingId: string, body: Record<string, unknown>) {
  return postJson(`/gateway/findings/${findingId}/poc`, body);
}

export function getAgentEvents(auditRunId: string, agentRunId: string) {
  return readJson(`/gateway/audit-runs/${auditRunId}/agent-runs/${agentRunId}/events`);
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
  return readJson(`/gateway/audit-runs/${auditRunId}/cleanup`, { method: "POST" });
}

export function cancelAuditRun(auditRunId: string) {
  return readJson(`/gateway/audit-runs/${auditRunId}/cancel`, { method: "POST" });
}

export function cleanupExpiredRuntime() {
  return readJson("/gateway/runtime/cleanup-expired", { method: "POST" });
}

export function previewLocalStorageCleanup() {
  return postJson("/gateway/runtime/storage/cleanup", { dry_run: true });
}

export function cleanupPlatformAuditEvents() {
  return readJson("/gateway/platform/audit-events", { method: "DELETE" });
}

export function createManagedApiKey(body: Record<string, unknown>) {
  return postJson("/gateway/auth/api-keys", body);
}

export function deactivateManagedApiKey(keyId: string) {
  return readJson(`/gateway/auth/api-keys/${keyId}/deactivate`, { method: "POST" });
}

export function uploadKnowledgeDocument(formData: FormData) {
  return readJson("/gateway/knowledge/documents", { method: "POST", body: formData });
}

export function searchKnowledge(body: Record<string, unknown>) {
  return postJson("/gateway/knowledge/search", body);
}

export function reindexKnowledgeDocument(documentId: string) {
  return readJson(`/gateway/knowledge/documents/${documentId}/reindex`, { method: "POST" });
}

export function deleteKnowledgeDocument(documentId: string) {
  return readJson(`/gateway/knowledge/documents/${documentId}`, { method: "DELETE" });
}

export async function fetchArtifactBlob(url: string) {
  const response = await fetch(url, withAuth());
  const text = response.ok ? undefined : await response.text();
  if (!response.ok) {
    throw new Error(formatHttpError(text || "", response.statusText));
  }
  return response.blob();
}

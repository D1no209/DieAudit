import { useMemo, useState } from "react";
import { getStoredApiKey } from "../api";
import type {
  AgentRun,
  AgentRunEvent,
  AgentModelConfig,
  AgentRuntimeAdapter,
  AgentTranscriptEvent,
  ApiHealth,
  ApiKeyRecord,
  AuthPrincipal,
  AuditRun,
  AuthStatus,
  CodeAnalysisTask,
  ContainerRow,
  DependencyInventory,
  DockerHealth,
  ExecutionGraph,
  Finding,
  FindingDetail,
  KnowledgeDocument,
  KnowledgeMatch,
  KnowledgeStatus,
  ManagedRuntime,
  PipelineStatus,
  PlatformAuditEvent,
  Project,
  ReportArtifact,
  RuntimePolicy,
  RuntimeReadiness,
  SandboxCapabilities,
  StorageSummary,
  WhiteboardGraph,
  WorkerHeartbeat,
} from "../types";

export function useDashboardState() {
  const [apiHealth, setApiHealth] = useState<ApiHealth>();
  const [authStatus, setAuthStatus] = useState<AuthStatus>();
  const [dockerHealth, setDockerHealth] = useState<DockerHealth>();
  const [managedRuntime, setManagedRuntime] = useState<ManagedRuntime>();
  const [storageSummary, setStorageSummary] = useState<StorageSummary>();
  const [runtimePolicy, setRuntimePolicy] = useState<RuntimePolicy>();
  const [runtimeReadiness, setRuntimeReadiness] = useState<RuntimeReadiness>();
  const [workerHeartbeats, setWorkerHeartbeats] = useState<WorkerHeartbeat[]>([]);
  const [sandboxCapabilities, setSandboxCapabilities] = useState<SandboxCapabilities>();
  const [apiKeys, setApiKeys] = useState<ApiKeyRecord[]>([]);
  const [agentModelConfig, setAgentModelConfig] = useState<AgentModelConfig>();
  const [platformAuditEvents, setPlatformAuditEvents] = useState<PlatformAuditEvent[]>([]);
  const [knowledgeDocuments, setKnowledgeDocuments] = useState<KnowledgeDocument[]>([]);
  const [knowledgeMatches, setKnowledgeMatches] = useState<KnowledgeMatch[]>([]);
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatus>();
  const [apiKey, setApiKey] = useState(() => getStoredApiKey());
  const [authPrincipal, setAuthPrincipal] = useState<AuthPrincipal>();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [auditRun, setAuditRun] = useState<AuditRun>();
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [agentRuntimes, setAgentRuntimes] = useState<AgentRuntimeAdapter[]>([]);
  const [codeAnalysisTasks, setCodeAnalysisTasks] = useState<CodeAnalysisTask[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [dependencies, setDependencies] = useState<DependencyInventory>();
  const [executionGraph, setExecutionGraph] = useState<ExecutionGraph>();
  const [containers, setContainers] = useState<ContainerRow[]>([]);
  const [reports, setReports] = useState<ReportArtifact[]>([]);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>();
  const [whiteboard, setWhiteboard] = useState<WhiteboardGraph>();
  const [selectedFinding, setSelectedFinding] = useState<FindingDetail>();
  const [agentEvents, setAgentEvents] = useState<AgentRunEvent[]>();
  const [agentMessages, setAgentMessages] = useState<AgentTranscriptEvent[]>([]);
  const [containerLogs, setContainerLogs] = useState<{ title: string; body: string }>();
  const [artifactPreview, setArtifactPreview] = useState<{ title: string; body: string }>();
  const [sandboxTarget, setSandboxTarget] = useState<{ network: string; target_url: string }>();
  const [lastResponse, setLastResponse] = useState<unknown>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [zipFiles, setZipFiles] = useState<File[]>([]);
  const [knowledgeFiles, setKnowledgeFiles] = useState<File[]>([]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.project_id === selectedProjectId),
    [projects, selectedProjectId],
  );

  function clearProtectedState() {
    setAuthPrincipal(undefined);
    setDockerHealth(undefined);
    setManagedRuntime(undefined);
    setStorageSummary(undefined);
    setRuntimePolicy(undefined);
    setRuntimeReadiness(undefined);
    setWorkerHeartbeats([]);
    setSandboxCapabilities(undefined);
    setApiKeys([]);
    setAgentModelConfig(undefined);
    setPlatformAuditEvents([]);
    setKnowledgeDocuments([]);
    setKnowledgeMatches([]);
    setKnowledgeStatus(undefined);
    setProjects([]);
    setSelectedProjectId(undefined);
    setAuditRun(undefined);
    setAgentRuns([]);
    setAgentRuntimes([]);
    setCodeAnalysisTasks([]);
    setFindings([]);
    setDependencies(undefined);
    setExecutionGraph(undefined);
    setContainers([]);
    setReports([]);
    setPipelineStatus(undefined);
    setWhiteboard(undefined);
    setSelectedFinding(undefined);
    setAgentEvents(undefined);
    setAgentMessages([]);
    setContainerLogs(undefined);
    setArtifactPreview(undefined);
    setSandboxTarget(undefined);
  }

  return {
    agentEvents,
    agentMessages,
    agentModelConfig,
    agentRuns,
    agentRuntimes,
    artifactPreview,
    apiHealth,
    apiKey,
    apiKeys,
    auditRun,
    authPrincipal,
    authStatus,
    clearProtectedState,
    codeAnalysisTasks,
    containerLogs,
    containers,
    dependencies,
    executionGraph,
    dockerHealth,
    error,
    findings,
    knowledgeDocuments,
    knowledgeFiles,
    knowledgeMatches,
    knowledgeStatus,
    lastResponse,
    loading,
    managedRuntime,
    pipelineStatus,
    platformAuditEvents,
    projects,
    reports,
    runtimePolicy,
    runtimeReadiness,
    sandboxCapabilities,
    sandboxTarget,
    selectedFinding,
    selectedProject,
    selectedProjectId,
    setAgentEvents,
    setAgentMessages,
    setAgentModelConfig,
    setArtifactPreview,
    setAgentRuns,
    setAgentRuntimes,
    setApiHealth,
    setApiKey,
    setApiKeys,
    setAuditRun,
    setAuthPrincipal,
    setAuthStatus,
    setCodeAnalysisTasks,
    setContainerLogs,
    setContainers,
    setDependencies,
    setExecutionGraph,
    setDockerHealth,
    setError,
    setFindings,
    setKnowledgeDocuments,
    setKnowledgeFiles,
    setKnowledgeMatches,
    setKnowledgeStatus,
    setLastResponse,
    setLoading,
    setManagedRuntime,
    setPipelineStatus,
    setWhiteboard,
    setPlatformAuditEvents,
    setProjects,
    setReports,
    setRuntimePolicy,
    setRuntimeReadiness,
    setSandboxCapabilities,
    setSandboxTarget,
    setSelectedFinding,
    setSelectedProjectId,
    setStorageSummary,
    setWorkerHeartbeats,
    setZipFiles,
    storageSummary,
    whiteboard,
    workerHeartbeats,
    zipFiles,
  };
}

export type DashboardStateController = ReturnType<typeof useDashboardState>;

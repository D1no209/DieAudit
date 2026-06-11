import { useMemo, useState } from "react";
import { Form } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { API_KEY_STORAGE_KEY } from "../api";
import type {
  AgentRun,
  AgentRunEvent,
  ApiHealth,
  ApiKeyRecord,
  AuditRun,
  AuthStatus,
  CodeAnalysisTask,
  ContainerRow,
  DependencyInventory,
  DockerHealth,
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
  const [platformAuditEvents, setPlatformAuditEvents] = useState<PlatformAuditEvent[]>([]);
  const [knowledgeDocuments, setKnowledgeDocuments] = useState<KnowledgeDocument[]>([]);
  const [knowledgeMatches, setKnowledgeMatches] = useState<KnowledgeMatch[]>([]);
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatus>();
  const [apiKey, setApiKey] = useState(() => window.localStorage.getItem(API_KEY_STORAGE_KEY) || "");
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [auditRun, setAuditRun] = useState<AuditRun>();
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [codeAnalysisTasks, setCodeAnalysisTasks] = useState<CodeAnalysisTask[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [dependencies, setDependencies] = useState<DependencyInventory>();
  const [containers, setContainers] = useState<ContainerRow[]>([]);
  const [reports, setReports] = useState<ReportArtifact[]>([]);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>();
  const [selectedFinding, setSelectedFinding] = useState<FindingDetail>();
  const [agentEvents, setAgentEvents] = useState<AgentRunEvent[]>();
  const [containerLogs, setContainerLogs] = useState<{ title: string; body: string }>();
  const [artifactPreview, setArtifactPreview] = useState<{ title: string; body: string }>();
  const [sandboxTarget, setSandboxTarget] = useState<{ network: string; target_url: string }>();
  const [lastResponse, setLastResponse] = useState<unknown>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [zipFiles, setZipFiles] = useState<UploadFile[]>([]);
  const [knowledgeFiles, setKnowledgeFiles] = useState<UploadFile[]>([]);
  const [gitForm] = Form.useForm();
  const [zipForm] = Form.useForm();
  const [apiKeyForm] = Form.useForm();
  const [knowledgeUploadForm] = Form.useForm();
  const [knowledgeSearchForm] = Form.useForm();

  const selectedProject = useMemo(
    () => projects.find((project) => project.project_id === selectedProjectId),
    [projects, selectedProjectId],
  );

  function clearProtectedState() {
    setDockerHealth(undefined);
    setManagedRuntime(undefined);
    setStorageSummary(undefined);
    setRuntimePolicy(undefined);
    setRuntimeReadiness(undefined);
    setWorkerHeartbeats([]);
    setSandboxCapabilities(undefined);
    setApiKeys([]);
    setPlatformAuditEvents([]);
    setKnowledgeDocuments([]);
    setKnowledgeMatches([]);
    setKnowledgeStatus(undefined);
    setProjects([]);
    setSelectedProjectId(undefined);
    setAuditRun(undefined);
    setAgentRuns([]);
    setCodeAnalysisTasks([]);
    setFindings([]);
    setDependencies(undefined);
    setContainers([]);
    setReports([]);
    setPipelineStatus(undefined);
    setSelectedFinding(undefined);
    setAgentEvents(undefined);
    setContainerLogs(undefined);
    setArtifactPreview(undefined);
    setSandboxTarget(undefined);
  }

  return {
    agentEvents,
    agentRuns,
    artifactPreview,
    apiHealth,
    apiKey,
    apiKeyForm,
    apiKeys,
    auditRun,
    authStatus,
    clearProtectedState,
    codeAnalysisTasks,
    containerLogs,
    containers,
    dependencies,
    dockerHealth,
    error,
    findings,
    gitForm,
    knowledgeDocuments,
    knowledgeFiles,
    knowledgeMatches,
    knowledgeSearchForm,
    knowledgeStatus,
    knowledgeUploadForm,
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
    setArtifactPreview,
    setAgentRuns,
    setApiHealth,
    setApiKey,
    setApiKeys,
    setAuditRun,
    setAuthStatus,
    setCodeAnalysisTasks,
    setContainerLogs,
    setContainers,
    setDependencies,
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
    workerHeartbeats,
    zipFiles,
    zipForm,
  };
}

export type DashboardStateController = ReturnType<typeof useDashboardState>;

import type { FormInstance } from "antd/es/form";
import type { UploadFile } from "antd/es/upload/interface";
import type { AppView } from "../navigation";
import { AdminPage } from "../pages/AdminPage";
import { FindingsPage } from "../pages/FindingsPage";
import { KnowledgePage } from "../pages/KnowledgePage";
import { OverviewPage } from "../pages/OverviewPage";
import { ProjectsPage } from "../pages/ProjectsPage";
import { RuntimePage } from "../pages/RuntimePage";
import type {
  AgentRun,
  ArtifactRef,
  AuditRun,
  AuthStatus,
  DependencyInventory,
  Finding,
  KnowledgeDocument,
  KnowledgeMatch,
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
  ContainerRow,
  ApiKeyRecord,
} from "../types";
import type { DashboardColumns } from "../hooks/useDashboardColumns";

type Props = {
  activeView: AppView;
  agentRuns: AgentRun[];
  apiHealth?: unknown;
  apiKeyForm: FormInstance;
  apiKeys: ApiKeyRecord[];
  auditRun?: AuditRun;
  authStatus?: AuthStatus;
  columns: DashboardColumns;
  containers: ContainerRow[];
  dependencies?: DependencyInventory;
  dockerHealth?: unknown;
  findings: Finding[];
  gitForm: FormInstance;
  knowledgeDocuments: KnowledgeDocument[];
  knowledgeFiles: UploadFile[];
  knowledgeMatches: KnowledgeMatch[];
  knowledgeSearchForm: FormInstance;
  knowledgeUploadForm: FormInstance;
  lastResponse?: unknown;
  loading: boolean;
  managedRuntime?: ManagedRuntime;
  pipelineStatus?: PipelineStatus;
  platformAuditEvents: PlatformAuditEvent[];
  projects: Project[];
  reports: ReportArtifact[];
  runtimePolicy?: RuntimePolicy;
  runtimeReadiness?: RuntimeReadiness;
  sandboxCapabilities?: SandboxCapabilities;
  sandboxTarget?: { network: string; target_url: string };
  selectedProject?: Project;
  selectedProjectId?: string;
  storageSummary?: StorageSummary;
  workerHeartbeats: WorkerHeartbeat[];
  zipFiles: UploadFile[];
  zipForm: FormInstance;
  onCancelAuditRun: () => void;
  onCleanup: () => void;
  onCleanupExpiredRuntime: () => void;
  onCleanupPlatformAuditEvents: () => void;
  onCreateGitProject: (values: { name: string; git_url: string; ref?: string }) => void;
  onCreateManagedApiKey: (values: { name: string; scopes?: string }) => void;
  onGenerateReport: () => void;
  onOpenArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onOpenFinding: (findingId: string) => void;
  onPreviewLocalStorageCleanup: () => void;
  onRunJudge: () => void;
  onRunPipeline: () => void;
  onRunPocSmoke: () => void;
  onRunSandboxTargetPoc: () => void;
  onRunSca: () => void;
  onSearchKnowledge: (values: { query: string; project_id?: string; limit?: string }) => void;
  onSelectProject: (projectId: string) => void;
  onSetKnowledgeFiles: (files: UploadFile[]) => void;
  onSetZipFiles: (files: UploadFile[]) => void;
  onStartAudit: () => void;
  onStartSandboxService: () => void;
  onUploadKnowledgeDocument: (values: { title: string; scope?: string; project_id?: string }) => void;
  onUploadZipProject: (values: { name: string }) => void;
};

export function AppRoutes(props: Props) {
  const { activeView, columns } = props;

  if (activeView === "overview") {
    return (
      <OverviewPage
        apiHealth={props.apiHealth}
        authStatus={props.authStatus}
        dockerHealth={props.dockerHealth}
        findingsCount={props.findings.length}
        managedRuntime={props.managedRuntime}
        projectsCount={props.projects.length}
        runtimeReadiness={props.runtimeReadiness}
        sandboxCapabilities={props.sandboxCapabilities}
      />
    );
  }

  if (activeView === "projects") {
    return (
      <ProjectsPage
        agentColumns={columns.agentColumns}
        agentRuns={props.agentRuns}
        auditRun={props.auditRun}
        gitForm={props.gitForm}
        lastResponse={props.lastResponse}
        loading={props.loading}
        pipelineStatus={props.pipelineStatus}
        projectColumns={columns.projectColumns}
        projects={props.projects}
        reports={props.reports}
        selectedProject={props.selectedProject}
        selectedProjectId={props.selectedProjectId}
        zipFiles={props.zipFiles}
        zipForm={props.zipForm}
        onCancelAuditRun={props.onCancelAuditRun}
        onCreateGitProject={props.onCreateGitProject}
        onGenerateReport={props.onGenerateReport}
        onOpenArtifact={props.onOpenArtifact}
        onRunJudge={props.onRunJudge}
        onRunPipeline={props.onRunPipeline}
        onRunSca={props.onRunSca}
        onSelectProject={props.onSelectProject}
        onSetZipFiles={props.onSetZipFiles}
        onStartAudit={props.onStartAudit}
        onUploadZipProject={props.onUploadZipProject}
      />
    );
  }

  if (activeView === "findings") {
    return <FindingsPage dependencies={props.dependencies} findings={props.findings} onOpenFinding={props.onOpenFinding} />;
  }

  if (activeView === "runtime") {
    return (
      <RuntimePage
        containerColumns={columns.containerColumns}
        containers={props.containers}
        loading={props.loading}
        runtimeReadiness={props.runtimeReadiness}
        sandboxTarget={props.sandboxTarget}
        workerColumns={columns.workerColumns}
        workerHeartbeats={props.workerHeartbeats}
        onCleanup={props.onCleanup}
        onCleanupExpiredRuntime={props.onCleanupExpiredRuntime}
        onRunPocSmoke={props.onRunPocSmoke}
        onRunSandboxTargetPoc={props.onRunSandboxTargetPoc}
        onStartSandboxService={props.onStartSandboxService}
      />
    );
  }

  if (activeView === "knowledge") {
    return (
      <KnowledgePage
        knowledgeColumns={columns.knowledgeColumns}
        knowledgeDocuments={props.knowledgeDocuments}
        knowledgeFiles={props.knowledgeFiles}
        knowledgeMatches={props.knowledgeMatches}
        knowledgeSearchForm={props.knowledgeSearchForm}
        knowledgeUploadForm={props.knowledgeUploadForm}
        loading={props.loading}
        selectedProjectId={props.selectedProjectId}
        onSearchKnowledge={props.onSearchKnowledge}
        onSetKnowledgeFiles={props.onSetKnowledgeFiles}
        onUploadKnowledgeDocument={props.onUploadKnowledgeDocument}
      />
    );
  }

  return (
    <AdminPage
      apiKeyColumns={columns.apiKeyColumns}
      apiKeyForm={props.apiKeyForm}
      apiKeys={props.apiKeys}
      loading={props.loading}
      platformAuditColumns={columns.platformAuditColumns}
      platformAuditEvents={props.platformAuditEvents}
      runtimePolicy={props.runtimePolicy}
      storageSummary={props.storageSummary}
      onCleanupPlatformAuditEvents={props.onCleanupPlatformAuditEvents}
      onCreateManagedApiKey={props.onCreateManagedApiKey}
      onPreviewLocalStorageCleanup={props.onPreviewLocalStorageCleanup}
    />
  );
}

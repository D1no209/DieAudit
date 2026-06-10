import type { ColumnsType } from "antd/es/table";
import type { FormInstance } from "antd/es/form";
import type { UploadFile } from "antd/es/upload/interface";
import type { Project } from "../types";
import { PageHeader } from "../components/PageHeader";
import { ProjectImportPanel } from "./projects/ProjectImportPanel";
import { ProjectInventoryTable } from "./projects/ProjectInventoryTable";
import { SelectedProjectPanel } from "./projects/SelectedProjectPanel";

type Props = {
  gitForm: FormInstance;
  loading: boolean;
  projectColumns: ColumnsType<Project>;
  projects: Project[];
  selectedProject?: Project;
  selectedProjectId?: string;
  zipFiles: UploadFile[];
  zipForm: FormInstance;
  onCreateGitProject: (values: { name: string; git_url: string; ref?: string }) => void;
  onSelectProject: (projectId: string) => void;
  onSetZipFiles: (files: UploadFile[]) => void;
  onUploadZipProject: (values: { name: string }) => void;
};

export function ProjectsPage({
  gitForm,
  loading,
  projectColumns,
  projects,
  selectedProject,
  selectedProjectId,
  zipFiles,
  zipForm,
  onCreateGitProject,
  onSelectProject,
  onSetZipFiles,
  onUploadZipProject,
}: Props) {
  return (
    <>
      <PageHeader title="Projects" />

      <div className="workspace-grid section">
        <ProjectImportPanel
          gitForm={gitForm}
          loading={loading}
          zipFiles={zipFiles}
          zipForm={zipForm}
          onCreateGitProject={onCreateGitProject}
          onSetZipFiles={onSetZipFiles}
          onUploadZipProject={onUploadZipProject}
        />
        <SelectedProjectPanel selectedProject={selectedProject} />
      </div>

      <ProjectInventoryTable
        projectColumns={projectColumns}
        projects={projects}
        selectedProjectId={selectedProjectId}
        onSelectProject={onSelectProject}
      />
    </>
  );
}

import type { Project } from "../types";
import type { DataColumn } from "../ui";
import { PageHeader } from "../components/PageHeader";
import { ProjectImportPanel } from "./projects/ProjectImportPanel";
import { ProjectInventoryTable } from "./projects/ProjectInventoryTable";
import { SelectedProjectPanel } from "./projects/SelectedProjectPanel";

type Props = {
  loading: boolean;
  projectColumns: DataColumn<Project>[];
  projects: Project[];
  selectedProject?: Project;
  selectedProjectId?: string;
  zipFiles: File[];
  onCreateGitProject: (values: { name: string; git_url: string; ref?: string }) => void;
  onSelectProject: (projectId: string) => void;
  onSetZipFiles: (files: File[]) => void;
  onUploadZipProject: (values: { name: string }) => void;
};

export function ProjectsPage({
  loading,
  projectColumns,
  projects,
  selectedProject,
  selectedProjectId,
  zipFiles,
  onCreateGitProject,
  onSelectProject,
  onSetZipFiles,
  onUploadZipProject,
}: Props) {
  return (
    <>
      <PageHeader title="Projects" />

      <div className="mb-5 grid gap-4 xl:grid-cols-[minmax(360px,0.9fr)_minmax(420px,1.1fr)]">
        <ProjectImportPanel
          loading={loading}
          zipFiles={zipFiles}
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

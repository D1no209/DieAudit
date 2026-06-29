import { Button, Field, FileDropzone, Input, Panel, fieldValue } from "../../ui";

type Props = {
  files: File[];
  loading: boolean;
  selectedProjectId?: string;
  onSetFiles: (files: File[]) => void;
  onUpload: (values: { title: string; scope?: string; project_id?: string }) => void;
};

export function KnowledgeUploadPanel({ files, loading, selectedProjectId, onSetFiles, onUpload }: Props) {
  return (
    <Panel title="Upload Document">
      <form
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          const formData = new FormData(event.currentTarget);
          onUpload({
            title: fieldValue(formData, "title") || "",
            scope: fieldValue(formData, "scope"),
            project_id: fieldValue(formData, "project_id"),
          });
          event.currentTarget.reset();
        }}
      >
        <Field label="Title"><Input name="title" required /></Field>
        <Field label="Scope"><Input name="scope" defaultValue="global" placeholder="global or project" /></Field>
        <Field label="Project ID"><Input name="project_id" placeholder={selectedProjectId || "optional for project scope"} /></Field>
        <FileDropzone onFilesChange={onSetFiles} />
        {files[0] ? <p className="text-sm text-slate-600">Selected: {files[0].name}</p> : null}
        <Button type="submit" variant="primary" loading={loading}>上传并索引</Button>
      </form>
    </Panel>
  );
}

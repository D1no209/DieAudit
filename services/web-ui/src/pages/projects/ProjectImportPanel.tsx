import { Button, Field, FileDropzone, Input, Panel, Tabs, fieldValue } from "../../ui";

type Props = {
  loading: boolean;
  zipFiles: File[];
  onCreateGitProject: (values: { name: string; git_url: string; ref?: string }) => void;
  onSetZipFiles: (files: File[]) => void;
  onUploadZipProject: (values: { name: string }) => void;
};

export function ProjectImportPanel({ loading, zipFiles, onCreateGitProject, onSetZipFiles, onUploadZipProject }: Props) {
  return (
    <Panel title="Import Project">
      <Tabs
        items={[
          {
            key: "git",
            label: "Git",
            children: (
              <form
                className="grid gap-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  const formData = new FormData(event.currentTarget);
                  onCreateGitProject({
                    name: fieldValue(formData, "name") || "",
                    git_url: fieldValue(formData, "git_url") || "",
                    ref: fieldValue(formData, "ref"),
                  });
                  event.currentTarget.reset();
                }}
              >
                <Field label="Name">
                  <Input name="name" required />
                </Field>
                <Field label="Git URL">
                  <Input name="git_url" required />
                </Field>
                <Field label="Ref">
                  <Input name="ref" />
                </Field>
                <Button type="submit" variant="primary" loading={loading}>
                  导入 Git
                </Button>
              </form>
            ),
          },
          {
            key: "zip",
            label: "Zip",
            children: (
              <form
                className="grid gap-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  const formData = new FormData(event.currentTarget);
                  onUploadZipProject({ name: fieldValue(formData, "name") || "" });
                  event.currentTarget.reset();
                }}
              >
                <Field label="Name">
                  <Input name="name" required />
                </Field>
                <FileDropzone accept=".zip,application/zip" onFilesChange={onSetZipFiles} />
                {zipFiles[0] ? <p className="text-sm text-slate-600">Selected: {zipFiles[0].name}</p> : null}
                <Button type="submit" variant="primary" loading={loading}>
                  上传 Zip
                </Button>
              </form>
            ),
          },
        ]}
      />
    </Panel>
  );
}

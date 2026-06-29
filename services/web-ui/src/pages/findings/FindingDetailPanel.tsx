import { FileText, ShieldCheck } from "lucide-react";
import type { ArtifactRef, FindingDetail, SandboxPocFormValues } from "../../types";
import { Accordion, Alert, Badge, Button, EmptyState, Field, NumberInput, Panel, SwitchField, Tabs, Textarea, Input, checkedFieldValue, fieldValue, numberFieldValue } from "../../ui";
import { severityColor, statusTone } from "../../utils/format";

type Props = {
  finding?: FindingDetail;
  loading: boolean;
  sandboxExecutionAvailable: boolean;
  sandboxUnavailableReason: string;
  onOpenArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onPreviewArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onRunFindingPoc: (values: SandboxPocFormValues) => void;
};

export function FindingDetailPanel({
  finding,
  loading,
  sandboxExecutionAvailable,
  sandboxUnavailableReason,
  onOpenArtifact,
  onPreviewArtifact,
  onRunFindingPoc,
}: Props) {
  if (!finding) {
    return (
      <Panel>
        <EmptyState description="Select a finding from the Findings page to review evidence, validation attempts, and PoC execution." />
      </Panel>
    );
  }

  return (
    <div className="grid gap-4">
      {!sandboxExecutionAvailable ? <Alert tone="warning" title="Sandbox execution is unavailable" description={sandboxUnavailableReason} /> : null}
      <Panel title={finding.finding.title}>
        <dl className="grid gap-3 text-sm">
          <InfoRow label="ID" value={finding.finding.finding_id} />
          <InfoRow label="Severity" value={<Badge tone={severityColor(finding.finding.severity)}>{finding.finding.severity}</Badge>} />
          <InfoRow label="Status" value={<Badge tone={statusTone(finding.finding.status)}>{finding.finding.status}</Badge>} />
          <InfoRow label="Location" value={`${finding.finding.file_path || "-"}:${finding.finding.line_start || "-"}`} />
          <InfoRow label="Source" value={finding.finding.source} />
          <InfoRow label="Description" value={finding.finding.description || "-"} />
          <InfoRow
            label="Tracking Markdown"
            value={
              <span className="flex flex-wrap items-center gap-2">
                <code className="text-xs">{finding.finding.finding_markdown?.relative_path || "-"}</code>
                <Button size="sm" icon={<FileText className="h-4 w-4" />} disabled={!finding.finding.finding_markdown} onClick={() => onPreviewArtifact(finding.finding.finding_markdown)}>预览</Button>
                <Button size="sm" icon={<FileText className="h-4 w-4" />} disabled={!finding.finding.finding_markdown} onClick={() => onOpenArtifact(finding.finding.finding_markdown)}>打开</Button>
              </span>
            }
          />
        </dl>
      </Panel>
      <Tabs
        items={[
          {
            key: "evidence",
            label: `Evidence (${finding.evidence.length})`,
            children: (
              <div className="grid gap-3">
                {finding.evidence.map((item) => (
                  <div key={item.evidence_id} className="rounded-lg border border-slate-200 bg-white p-3">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <span className="flex flex-wrap items-center gap-2">
                        <Badge>{item.kind}</Badge>
                        <span className="font-medium text-slate-900">{item.summary || item.artifact?.name || item.evidence_id}</span>
                      </span>
                      <span className="flex gap-2">
                        <Button size="sm" icon={<FileText className="h-4 w-4" />} disabled={!item.artifact && !item.artifact_path} onClick={() => onPreviewArtifact(item.artifact, item.artifact_path)}>预览</Button>
                        <Button size="sm" icon={<FileText className="h-4 w-4" />} disabled={!item.artifact && !item.artifact_path} onClick={() => onOpenArtifact(item.artifact, item.artifact_path)}>下载</Button>
                      </span>
                    </div>
                    <pre>{JSON.stringify(item, null, 2)}</pre>
                  </div>
                ))}
              </div>
            ),
          },
          { key: "attempts", label: `Validation Attempts (${finding.validation_attempts.length})`, children: <pre>{JSON.stringify(finding.validation_attempts, null, 2)}</pre> },
          {
            key: "poc",
            label: "PoC Execution",
            children: (
              <form
                className="grid gap-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  const formData = new FormData(event.currentTarget);
                  onRunFindingPoc({
                    image: fieldValue(formData, "image") || "",
                    command: fieldValue(formData, "command") || "",
                    timeout_seconds: numberFieldValue(formData, "timeout_seconds"),
                    expected_exit_code: numberFieldValue(formData, "expected_exit_code"),
                    mount_workspace: checkedFieldValue(formData, "mount_workspace"),
                    retain_runtime_on_failure: checkedFieldValue(formData, "retain_runtime_on_failure"),
                  });
                }}
              >
                <Field label="Image"><Input name="image" required defaultValue="python:3.12-slim" /></Field>
                <Field label="Command"><Textarea name="command" required rows={5} placeholder={"python\n-c\nprint('project-specific PoC')"} /></Field>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Timeout"><NumberInput name="timeout_seconds" min={1} max={3600} defaultValue={120} /></Field>
                  <Field label="Expected Exit"><NumberInput name="expected_exit_code" defaultValue={0} /></Field>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <SwitchField name="mount_workspace" label="Mount Workspace" defaultChecked />
                  <SwitchField name="retain_runtime_on_failure" label="Retain On Failure" />
                </div>
                <Button
                  icon={<ShieldCheck className="h-4 w-4" />}
                  loading={loading}
                  type="submit"
                  variant="primary"
                  disabled={!sandboxExecutionAvailable}
                  title={sandboxExecutionAvailable ? undefined : sandboxUnavailableReason}
                >
                  Run PoC
                </Button>
              </form>
            ),
          },
          { key: "raw", label: "Raw", children: <pre>{JSON.stringify(finding.finding.raw || {}, null, 2)}</pre> },
        ]}
      />
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid gap-1">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="text-slate-800">{value}</dd>
    </div>
  );
}

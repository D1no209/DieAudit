import type { AuditRun, SandboxCapabilities, SandboxPocFormValues, SandboxServiceFormValues } from "../../types";
import { Alert, Button, Field, Input, NumberInput, Panel, SwitchField, Textarea, checkedFieldValue, fieldValue, numberFieldValue } from "../../ui";

type Props = {
  auditRun?: AuditRun;
  loading: boolean;
  sandboxCapabilities?: SandboxCapabilities;
  sandboxTarget?: { network: string; target_url: string };
  sandboxUnavailableReason: string;
  onRunSandboxPoc: (values: SandboxPocFormValues) => void;
  onRunSandboxTargetPoc: (values: SandboxPocFormValues) => void;
  onStartSandboxService: (values: SandboxServiceFormValues) => void;
};

export function RuntimeSandboxPanel({
  auditRun,
  loading,
  sandboxCapabilities,
  sandboxTarget,
  sandboxUnavailableReason,
  onRunSandboxPoc,
  onRunSandboxTargetPoc,
  onStartSandboxService,
}: Props) {
  const sandboxExecutionAvailable = Boolean(sandboxCapabilities?.sandbox_execution_available);
  const weakIsolation = Boolean(sandboxCapabilities?.sandbox_execution_available && !sandboxCapabilities?.strong_isolation_available);

  function parsePocForm(form: HTMLFormElement): SandboxPocFormValues {
    const formData = new FormData(form);
    return {
      image: fieldValue(formData, "image") || "",
      command: fieldValue(formData, "command") || "",
      timeout_seconds: numberFieldValue(formData, "timeout_seconds"),
      expected_exit_code: numberFieldValue(formData, "expected_exit_code"),
      target_url: fieldValue(formData, "target_url"),
      mount_workspace: checkedFieldValue(formData, "mount_workspace"),
      retain_runtime_on_failure: checkedFieldValue(formData, "retain_runtime_on_failure"),
    };
  }

  return (
    <div className="grid gap-4">
      {!sandboxExecutionAvailable ? <Alert tone="warning" title="Sandbox execution is unavailable" description={sandboxUnavailableReason} /> : null}
      {weakIsolation ? (
        <Alert
          tone="warning"
          title="Sandbox is using weak isolation"
          description="ALLOW_RUNC_SANDBOX is enabled. Use this only for local trusted testing, not untrusted PoC execution."
        />
      ) : null}
      {!auditRun ? <Alert tone="warning" title="Create or select an AuditRun before starting sandbox execution." /> : null}
      {sandboxTarget ? <Alert tone="processing" title="Sandbox target is running" description={`${sandboxTarget.target_url} on ${sandboxTarget.network}`} /> : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Target Service">
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              const formData = new FormData(event.currentTarget);
              onStartSandboxService({
                image: fieldValue(formData, "image") || "",
                command: fieldValue(formData, "command") || "",
                service_name: fieldValue(formData, "service_name"),
                port: numberFieldValue(formData, "port"),
                healthcheck_path: fieldValue(formData, "healthcheck_path"),
                startup_timeout_seconds: numberFieldValue(formData, "startup_timeout_seconds"),
                mount_workspace: checkedFieldValue(formData, "mount_workspace"),
                retain_runtime_on_failure: checkedFieldValue(formData, "retain_runtime_on_failure"),
              });
            }}
          >
            <Field label="Image"><Input name="image" required defaultValue="python:3.12-slim" placeholder="registry.example.com/app-under-test:latest" /></Field>
            <Field label="Command"><Textarea name="command" required rows={5} placeholder={"python\n-m\nhttp.server\n8080"} /></Field>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Service"><Input name="service_name" required defaultValue="target" /></Field>
              <Field label="Port"><NumberInput name="port" min={1} max={65535} defaultValue={8080} /></Field>
              <Field label="Startup Timeout"><NumberInput name="startup_timeout_seconds" min={1} max={300} defaultValue={30} /></Field>
            </div>
            <Field label="Healthcheck Path"><Input name="healthcheck_path" placeholder="/health" /></Field>
            <div className="grid gap-2 sm:grid-cols-2">
              <SwitchField name="mount_workspace" label="Mount Workspace" defaultChecked />
              <SwitchField name="retain_runtime_on_failure" label="Retain On Failure" defaultChecked />
            </div>
            <Button type="submit" variant="primary" loading={loading} disabled={!auditRun || !sandboxExecutionAvailable}>Start Service</Button>
          </form>
        </Panel>

        <Panel title="PoC Execution">
          <form
            className="grid gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              onRunSandboxPoc(parsePocForm(event.currentTarget));
            }}
          >
            <Field label="Image"><Input name="image" required defaultValue="python:3.12-slim" placeholder="python:3.12-slim" /></Field>
            <Field label="Command"><Textarea name="command" required rows={5} placeholder={"python\n-c\nprint('ok')"} /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Timeout"><NumberInput name="timeout_seconds" min={1} max={3600} defaultValue={120} /></Field>
              <Field label="Expected Exit"><NumberInput name="expected_exit_code" defaultValue={0} /></Field>
            </div>
            <Field label="Target URL"><Input name="target_url" placeholder={sandboxTarget?.target_url || "optional"} /></Field>
            <div className="grid gap-2 sm:grid-cols-2">
              <SwitchField name="mount_workspace" label="Mount Workspace" defaultChecked />
              <SwitchField name="retain_runtime_on_failure" label="Retain On Failure" />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" variant="primary" loading={loading} disabled={!auditRun || !sandboxExecutionAvailable}>Run PoC</Button>
              <Button
                loading={loading}
                disabled={!auditRun || !sandboxExecutionAvailable || !sandboxTarget}
                onClick={(event) => {
                  const form = event.currentTarget.closest("form");
                  if (form) onRunSandboxTargetPoc(parsePocForm(form));
                }}
              >
                Run Against Target
              </Button>
            </div>
          </form>
        </Panel>
      </div>
    </div>
  );
}

import type { AuditRun, SandboxCapabilities, SandboxPocFormValues, SandboxServiceFormValues } from "../types";
import { PageHeader } from "../components/PageHeader";
import { Alert } from "../ui";
import { RuntimeSandboxPanel } from "./runtime/RuntimeSandboxPanel";

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

export function RuntimeSandboxPage({
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

  return (
    <>
      <PageHeader title="Runtime Sandbox" />
      {!sandboxExecutionAvailable && (
        <Alert
          className="mb-5"
          tone="warning"
          title="Sandbox execution is unavailable"
          description={sandboxUnavailableReason}
        />
      )}
      <RuntimeSandboxPanel
        auditRun={auditRun}
        loading={loading}
        sandboxCapabilities={sandboxCapabilities}
        sandboxTarget={sandboxTarget}
        sandboxUnavailableReason={sandboxUnavailableReason}
        onRunSandboxPoc={onRunSandboxPoc}
        onRunSandboxTargetPoc={onRunSandboxTargetPoc}
        onStartSandboxService={onStartSandboxService}
      />
    </>
  );
}

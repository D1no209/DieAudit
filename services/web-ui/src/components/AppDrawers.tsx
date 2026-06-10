import type { AgentRunEvent, ArtifactRef, FindingDetail } from "../types";
import { AgentEventsDrawer } from "./drawers/AgentEventsDrawer";
import { ContainerLogsDrawer } from "./drawers/ContainerLogsDrawer";
import { FindingDrawer } from "./drawers/FindingDrawer";

type Props = {
  agentEvents?: AgentRunEvent[];
  containerLogs?: { title: string; body: string };
  loading: boolean;
  sandboxExecutionAvailable: boolean;
  sandboxUnavailableReason: string;
  selectedFinding?: FindingDetail;
  onCloseAgentEvents: () => void;
  onCloseContainerLogs: () => void;
  onCloseFinding: () => void;
  onOpenArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onRunFindingPoc: () => void;
};

export function AppDrawers({
  agentEvents,
  containerLogs,
  loading,
  sandboxExecutionAvailable,
  sandboxUnavailableReason,
  selectedFinding,
  onCloseAgentEvents,
  onCloseContainerLogs,
  onCloseFinding,
  onOpenArtifact,
  onRunFindingPoc,
}: Props) {
  return (
    <>
      <FindingDrawer
        finding={selectedFinding}
        loading={loading}
        sandboxExecutionAvailable={sandboxExecutionAvailable}
        sandboxUnavailableReason={sandboxUnavailableReason}
        onClose={onCloseFinding}
        onOpenArtifact={onOpenArtifact}
        onRunFindingPoc={onRunFindingPoc}
      />
      <AgentEventsDrawer events={agentEvents} onClose={onCloseAgentEvents} />
      <ContainerLogsDrawer logs={containerLogs} onClose={onCloseContainerLogs} />
    </>
  );
}

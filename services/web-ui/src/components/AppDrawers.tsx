import type { AgentRunEvent } from "../types";
import { AgentEventsDrawer } from "./drawers/AgentEventsDrawer";
import { ArtifactPreviewDrawer } from "./drawers/ArtifactPreviewDrawer";
import { ContainerLogsDrawer } from "./drawers/ContainerLogsDrawer";

type Props = {
  agentEvents?: AgentRunEvent[];
  artifactPreview?: { title: string; body: string };
  containerLogs?: { title: string; body: string };
  onCloseAgentEvents: () => void;
  onCloseArtifactPreview: () => void;
  onCloseContainerLogs: () => void;
};

export function AppDrawers({
  agentEvents,
  artifactPreview,
  containerLogs,
  onCloseAgentEvents,
  onCloseArtifactPreview,
  onCloseContainerLogs,
}: Props) {
  return (
    <>
      <AgentEventsDrawer events={agentEvents} onClose={onCloseAgentEvents} />
      <ArtifactPreviewDrawer preview={artifactPreview} onClose={onCloseArtifactPreview} />
      <ContainerLogsDrawer logs={containerLogs} onClose={onCloseContainerLogs} />
    </>
  );
}

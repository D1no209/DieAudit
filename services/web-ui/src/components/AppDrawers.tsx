import type { AgentRunEvent } from "../types";
import { AgentEventsDrawer } from "./drawers/AgentEventsDrawer";
import { ContainerLogsDrawer } from "./drawers/ContainerLogsDrawer";

type Props = {
  agentEvents?: AgentRunEvent[];
  containerLogs?: { title: string; body: string };
  onCloseAgentEvents: () => void;
  onCloseContainerLogs: () => void;
};

export function AppDrawers({
  agentEvents,
  containerLogs,
  onCloseAgentEvents,
  onCloseContainerLogs,
}: Props) {
  return (
    <>
      <AgentEventsDrawer events={agentEvents} onClose={onCloseAgentEvents} />
      <ContainerLogsDrawer logs={containerLogs} onClose={onCloseContainerLogs} />
    </>
  );
}

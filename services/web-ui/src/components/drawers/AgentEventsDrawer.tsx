import { Drawer } from "antd";
import type { AgentRunEvent } from "../../types";

type Props = {
  events?: AgentRunEvent[];
  onClose: () => void;
};

export function AgentEventsDrawer({ events, onClose }: Props) {
  return (
    <Drawer title="Agent Events" open={Boolean(events)} width={720} onClose={onClose}>
      <pre>{JSON.stringify(events || [], null, 2)}</pre>
    </Drawer>
  );
}

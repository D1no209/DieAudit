import type { AgentRunEvent } from "../../types";
import { Drawer } from "../../ui";

export function AgentEventsDrawer({ events, onClose }: { events?: AgentRunEvent[]; onClose: () => void }) {
  return (
    <Drawer open={Boolean(events)} onOpenChange={(open) => !open && onClose()} title="Agent Events">
      <pre>{JSON.stringify(events || [], null, 2)}</pre>
    </Drawer>
  );
}

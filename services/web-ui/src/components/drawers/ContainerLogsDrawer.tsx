import { Drawer } from "../../ui";

export function ContainerLogsDrawer({ logs, onClose }: { logs?: { title: string; body: string }; onClose: () => void }) {
  return (
    <Drawer open={Boolean(logs)} onOpenChange={(open) => !open && onClose()} title={logs?.title || "Container Logs"}>
      <pre>{logs?.body || ""}</pre>
    </Drawer>
  );
}

import { Drawer } from "antd";

type Props = {
  logs?: { title: string; body: string };
  onClose: () => void;
};

export function ContainerLogsDrawer({ logs, onClose }: Props) {
  return (
    <Drawer title={`Container Logs - ${logs?.title || ""}`} open={Boolean(logs)} width={820} onClose={onClose}>
      <pre>{logs?.body || ""}</pre>
    </Drawer>
  );
}

import { Drawer } from "antd";

type Props = {
  preview?: { title: string; body: string };
  onClose: () => void;
};

export function ArtifactPreviewDrawer({ preview, onClose }: Props) {
  return (
    <Drawer title={`Artifact Preview - ${preview?.title || ""}`} open={Boolean(preview)} width={920} onClose={onClose}>
      <pre>{preview?.body || ""}</pre>
    </Drawer>
  );
}

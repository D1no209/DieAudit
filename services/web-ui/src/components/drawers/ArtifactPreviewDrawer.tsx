import { Drawer } from "../../ui";

export function ArtifactPreviewDrawer({ preview, onClose }: { preview?: { title: string; body: string }; onClose: () => void }) {
  return (
    <Drawer open={Boolean(preview)} onOpenChange={(open) => !open && onClose()} title={preview?.title || "Artifact Preview"}>
      <pre>{preview?.body || ""}</pre>
    </Drawer>
  );
}

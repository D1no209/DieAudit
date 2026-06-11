import { Button } from "antd";
import { BugOutlined } from "@ant-design/icons";
import type { ArtifactRef, FindingDetail, SandboxPocFormValues } from "../types";
import { PageHeader } from "../components/PageHeader";
import { FindingDetailPanel } from "./findings/FindingDetailPanel";

type Props = {
  loading: boolean;
  sandboxExecutionAvailable: boolean;
  sandboxUnavailableReason: string;
  selectedFinding?: FindingDetail;
  onOpenArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onPreviewArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onRunFindingPoc: (values: SandboxPocFormValues) => void;
  onViewFindings: () => void;
};

export function FindingReviewPage({
  loading,
  sandboxExecutionAvailable,
  sandboxUnavailableReason,
  selectedFinding,
  onOpenArtifact,
  onPreviewArtifact,
  onRunFindingPoc,
  onViewFindings,
}: Props) {
  const pageActions = (
    <div className="action-bar">
      <Button icon={<BugOutlined />} onClick={onViewFindings}>
        返回 Findings
      </Button>
    </div>
  );

  return (
    <>
      <PageHeader title="Finding Review" actions={pageActions} />
      <FindingDetailPanel
        finding={selectedFinding}
        loading={loading}
        sandboxExecutionAvailable={sandboxExecutionAvailable}
        sandboxUnavailableReason={sandboxUnavailableReason}
        onOpenArtifact={onOpenArtifact}
        onPreviewArtifact={onPreviewArtifact}
        onRunFindingPoc={onRunFindingPoc}
      />
    </>
  );
}

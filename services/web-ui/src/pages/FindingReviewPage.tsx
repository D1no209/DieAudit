import { Bug } from "lucide-react";
import type { ArtifactRef, FindingDetail, SandboxPocFormValues } from "../types";
import { PageHeader } from "../components/PageHeader";
import { Button } from "../ui";
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
    <div className="flex flex-wrap gap-2">
      <Button icon={<Bug className="h-4 w-4" />} onClick={onViewFindings}>返回 Findings</Button>
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

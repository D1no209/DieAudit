import { FileText } from "lucide-react";
import type { ArtifactRef, AuditRun, ReportArtifact } from "../types";
import { Alert, Badge, Button, EmptyState, Panel } from "../ui";
import { PageHeader } from "../components/PageHeader";

type Props = {
  auditRun?: AuditRun;
  loading: boolean;
  reports: ReportArtifact[];
  onGenerateReport: () => void;
  onOpenArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
  onPreviewArtifact: (artifact?: ArtifactRef, fallbackPath?: string) => void;
};

export function ReportsPage({ auditRun, loading, reports, onGenerateReport, onOpenArtifact, onPreviewArtifact }: Props) {
  const pageActions = (
    <div className="flex flex-wrap gap-2">
      <Button icon={<FileText className="h-4 w-4" />} loading={loading} disabled={!auditRun} onClick={onGenerateReport}>生成报告</Button>
    </div>
  );

  return (
    <>
      <PageHeader title="Reports" eyebrow="Deliver" actions={pageActions} />
      {!auditRun ? (
        <Alert className="mb-5" tone="processing" title="No active AuditRun" description="Create or select an audit run before generating reports." />
      ) : null}
      <Panel title="Report Artifacts" actions={<Badge>{auditRun?.audit_run_id || "No run"}</Badge>} dense>
        {reports.length ? (
          <div className="grid gap-3">
            {reports.map((item) => (
              <div key={item.report_id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-300 bg-slate-50 p-3">
                <div className="min-w-0">
                  <div className="font-medium text-slate-900">{item.kind}</div>
                  <div className="truncate text-sm text-slate-500">{item.artifact?.relative_path || item.path}</div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>{String(item.summary?.finding_count ?? 0)} findings</Badge>
                  <Badge>{String(item.summary?.parse_warning_count ?? 0)} parse warnings</Badge>
                  <Badge>{String(item.summary?.tool_failure_count ?? 0)} tool failures</Badge>
                  <Button size="sm" icon={<FileText className="h-4 w-4" />} onClick={() => onPreviewArtifact(item.artifact, item.path)}>预览</Button>
                  <Button size="sm" icon={<FileText className="h-4 w-4" />} onClick={() => onOpenArtifact(item.artifact, item.path)}>下载</Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState description="No report artifacts yet" />
        )}
      </Panel>
    </>
  );
}

import { useCallback, useState } from "react";
import { auditRunsApi, type BffAuditRun, type CreateAuditRunPayload } from "../../api/auditRuns";

export function useAuditRunsDomain() {
  const [auditRuns, setAuditRuns] = useState<BffAuditRun[]>([]);
  const [selectedAuditRun, setSelectedAuditRun] = useState<BffAuditRun>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      setAuditRuns(await auditRunsApi.list());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const create = useCallback(async (payload: CreateAuditRunPayload) => {
    const auditRun = await auditRunsApi.create(payload);
    setAuditRuns((current) => [auditRun, ...current]);
    setSelectedAuditRun(auditRun);
    return auditRun;
  }, []);

  const start = useCallback(async (auditRunId: string) => {
    const result = await auditRunsApi.start(auditRunId);
    setSelectedAuditRun(result.audit_run);
    return result;
  }, []);

  return { auditRuns, selectedAuditRun, loading, error, refresh, create, start, setSelectedAuditRun };
}

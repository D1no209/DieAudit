import { useCallback, useState } from "react";
import { adminApi } from "../../api/admin";

export function useAdminDomain() {
  const [auditEvents, setAuditEvents] = useState<unknown[]>([]);

  const refresh = useCallback(async () => {
    setAuditEvents(await adminApi.auditEvents());
  }, []);

  return { auditEvents, refresh };
}

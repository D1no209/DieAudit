import { useCallback, useState } from "react";
import { runtimeApi } from "../../api/runtime";

export function useRuntimeDomain() {
  const [readiness, setReadiness] = useState<Record<string, unknown>>();
  const [managed, setManaged] = useState<Record<string, unknown>>();

  const refresh = useCallback(async () => {
    const [nextReadiness, nextManaged] = await Promise.all([runtimeApi.readiness(), runtimeApi.managed()]);
    setReadiness(nextReadiness);
    setManaged(nextManaged);
  }, []);

  return { readiness, managed, refresh };
}

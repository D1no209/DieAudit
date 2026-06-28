import { useCallback, useState } from "react";
import { findingsApi } from "../../api/findings";

export function useFindingsDomain() {
  const [findings, setFindings] = useState<unknown[]>([]);

  const refresh = useCallback(async () => {
    setFindings(await findingsApi.list());
  }, []);

  return { findings, refresh };
}

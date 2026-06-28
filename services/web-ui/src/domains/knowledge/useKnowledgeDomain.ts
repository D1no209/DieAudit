import { useCallback, useState } from "react";
import { knowledgeApi } from "../../api/knowledge";

export function useKnowledgeDomain() {
  const [documents, setDocuments] = useState<unknown[]>([]);
  const [status, setStatus] = useState<Record<string, unknown>>();

  const refresh = useCallback(async () => {
    const [nextDocuments, nextStatus] = await Promise.all([knowledgeApi.documents(), knowledgeApi.status()]);
    setDocuments(nextDocuments);
    setStatus(nextStatus);
  }, []);

  return { documents, status, refresh };
}

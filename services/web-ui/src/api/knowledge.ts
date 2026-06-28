import { bffGet } from "./bffClient";

export const knowledgeApi = {
  documents: () => bffGet<unknown[]>("/knowledge/documents"),
  status: () => bffGet<Record<string, unknown>>("/knowledge/status"),
};

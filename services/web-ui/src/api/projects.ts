import { bffGet, bffPost } from "./bffClient";

export type BffProject = {
  project_id: string;
  name: string;
  source_type: string;
  source_uri?: string;
  status: string;
  metadata: Record<string, unknown>;
};

export type CreateProjectPayload = {
  name: string;
  git_url?: string;
  ref?: string;
  metadata?: Record<string, unknown>;
};

export const projectsApi = {
  list: () => bffGet<BffProject[]>("/projects"),
  create: (payload: CreateProjectPayload) => bffPost<BffProject>("/projects", payload),
};

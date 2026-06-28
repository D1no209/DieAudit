import { useCallback, useState } from "react";
import { projectsApi, type BffProject, type CreateProjectPayload } from "../../api/projects";

export function useProjectsDomain() {
  const [projects, setProjects] = useState<BffProject[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      setProjects(await projectsApi.list());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const create = useCallback(async (payload: CreateProjectPayload) => {
    const project = await projectsApi.create(payload);
    setProjects((current) => [project, ...current]);
    return project;
  }, []);

  return { projects, loading, error, refresh, create };
}

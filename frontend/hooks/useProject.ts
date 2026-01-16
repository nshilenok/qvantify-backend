import { useCallback, useEffect, useState } from "react";
import { fetchProject } from "@/lib/api";
import type { ProjectConfig } from "@/lib/types";

export const useProject = (projectId: string | null) => {
  const [project, setProject] = useState<ProjectConfig | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(projectId));
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) {
      setProject(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchProject(projectId);
      setProject(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load project";
      setError(message);
      setProject(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  return {
    project,
    loading,
    error,
    refresh: load,
  };
};

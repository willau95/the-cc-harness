import { api } from "./client";
import type { ProjectDetailResponse, ProjectsResponse } from "./types";

export const projectsApi = {
  list: () => api.get<ProjectsResponse>("/projects"),
  get: (proj: string) => api.get<ProjectDetailResponse>(`/projects/${encodeURIComponent(proj)}`),
};

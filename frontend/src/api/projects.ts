import { api } from "./client";

export interface ProjectCreate {
  title: string;
  client_name?: string;
  description?: string;
}

export interface ProjectUpdate {
  title?: string;
  client_name?: string;
  description?: string;
  status?: string;
}

export const projectsApi = {
  list: (status?: string) =>
    api.get("/projects", { params: status ? { status } : undefined }),
  get: (id: string) => api.get(`/projects/${id}`),
  create: (data: ProjectCreate) => api.post("/projects", data),
  update: (id: string, data: ProjectUpdate) => api.patch(`/projects/${id}`, data),
  delete: (id: string) => api.delete(`/projects/${id}`),
};

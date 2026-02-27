import { api } from "./client";

export const documentsApi = {
  list: (projectId?: string) =>
    api.get("/documents", { params: projectId ? { project_id: projectId } : undefined }),
  upload: (file: File, projectId?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (projectId) form.append("project_id", projectId);
    return api.post("/documents/upload", form);
  },
  delete: (id: string) => api.delete(`/documents/${id}`),
};

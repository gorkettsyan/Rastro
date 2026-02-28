import { api } from "./client";

export const documentsApi = {
  list: (projectId?: string, opts?: { include_emails?: boolean; source?: string }) =>
    api.get("/documents", {
      params: {
        ...(projectId ? { project_id: projectId } : {}),
        ...(opts?.include_emails ? { include_emails: true } : {}),
        ...(opts?.source ? { source: opts.source } : {}),
      },
    }),
  upload: (file: File, projectId?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (projectId) form.append("project_id", projectId);
    return api.post("/documents/upload", form);
  },
  delete: (id: string) => api.delete(`/documents/${id}`),
};

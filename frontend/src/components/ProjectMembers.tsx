import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";

interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  role: string;
}

interface TeamUser {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
}

export default function ProjectMembers({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedUserId, setSelectedUserId] = useState("");
  const [memberRole, setMemberRole] = useState("viewer");

  const { data: members } = useQuery({
    queryKey: ["project-members", projectId],
    queryFn: () =>
      api.get(`/projects/${projectId}/members`).then((r) => r.data.items as Member[]),
  });

  const { data: teamUsers } = useQuery({
    queryKey: ["team"],
    queryFn: () => api.get("/team").then((r) => r.data.items as TeamUser[]),
  });

  const addMutation = useMutation({
    mutationFn: (data: { user_id: string; role: string }) =>
      api.post(`/projects/${projectId}/members`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-members", projectId] });
      setSelectedUserId("");
    },
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) =>
      api.delete(`/projects/${projectId}/members/${userId}`),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["project-members", projectId] }),
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      api.patch(`/projects/${projectId}/members/${userId}/role`, { role }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["project-members", projectId] }),
  });

  const existingUserIds = new Set(members?.map((m) => m.user_id) || []);
  const availableUsers = teamUsers?.filter((u) => !existingUserIds.has(u.id)) || [];

  return (
    <div className="r-section">
      <div className="r-section-header">
        <p className="r-section-label">{t("members")}</p>
      </div>

      {members && members.length > 0 ? (
        <div className="r-doc-list">
          {members.map((m) => (
            <div key={m.id} className="r-member-row">
              <div className="r-member-info">
                <span className="r-member-name">{m.full_name || m.email}</span>
                {m.full_name && (
                  <span className="r-member-email">{m.email}</span>
                )}
              </div>
              <select
                className="r-role-select"
                value={m.role}
                data-role={m.role}
                onChange={(e) => roleMutation.mutate({ userId: m.user_id, role: e.target.value })}
              >
                <option value="owner">{t("role_owner")}</option>
                <option value="editor">{t("role_editor")}</option>
                <option value="viewer">{t("role_viewer")}</option>
              </select>
              <button
                className="r-btn-icon-danger"
                onClick={() => removeMutation.mutate(m.user_id)}
                title={t("remove")}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="r-empty">
          <p className="r-empty-title">{t("no_members")}</p>
        </div>
      )}

      {/* Add member */}
      {availableUsers.length > 0 && (
        <div className="r-invite-row" style={{ marginTop: "var(--space-md)" }}>
          <select
            className="r-select"
            value={selectedUserId}
            onChange={(e) => setSelectedUserId(e.target.value)}
          >
            <option value="">{t("select_member")}</option>
            {availableUsers.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name || u.email}
              </option>
            ))}
          </select>
          <select
            className="r-select"
            value={memberRole}
            onChange={(e) => setMemberRole(e.target.value)}
          >
            <option value="viewer">{t("role_viewer")}</option>
            <option value="editor">{t("role_editor")}</option>
            <option value="owner">{t("role_owner")}</option>
          </select>
          <button
            className="r-btn-primary"
            disabled={!selectedUserId || addMutation.isPending}
            onClick={() => addMutation.mutate({ user_id: selectedUserId, role: memberRole })}
          >
            {t("add_member")}
          </button>
        </div>
      )}
    </div>
  );
}

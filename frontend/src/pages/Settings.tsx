import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import Header from "../components/Header";

interface TeamMember {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
}

interface Invite {
  id: string;
  email: string;
  role: string;
  token: string;
  expires_at: string;
}

export default function Settings() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [inviteError, setInviteError] = useState("");

  const { data: team } = useQuery({
    queryKey: ["team"],
    queryFn: () => api.get("/team").then((r) => r.data.items as TeamMember[]),
  });

  const { data: invites } = useQuery({
    queryKey: ["invites"],
    queryFn: () => api.get("/team/invites").then((r) => r.data.items as Invite[]),
  });

  const inviteMutation = useMutation({
    mutationFn: (data: { email: string; role: string }) =>
      api.post("/team/invite", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invites"] });
      setEmail("");
      setInviteError("");
    },
    onError: (err: any) => {
      setInviteError(err.response?.data?.detail || t("error"));
    },
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) => api.delete(`/team/members/${userId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team"] }),
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      api.patch(`/team/members/${userId}/role`, { role }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["team"] }),
  });

  return (
    <div className="r-page">
      <Header />
      <main className="r-main">
        <h2 className="r-page-title">{t("settings")}</h2>

        {/* Team roster */}
        <div className="r-section">
          <div className="r-section-header">
            <p className="r-section-label">{t("team_members")}</p>
          </div>
          {team && team.length > 0 ? (
            <div className="r-doc-list">
              {team.map((m) => (
                <div key={m.id} className="r-doc-row">
                  <span className="r-doc-title">
                    {m.full_name || m.email}
                    {m.full_name && (
                      <span style={{ color: "var(--ink-muted)", marginLeft: 8, fontSize: 12 }}>
                        {m.email}
                      </span>
                    )}
                  </span>
                  <span className={`r-pill r-pill-role-${m.role}`}>{t(`role_${m.role}`)}</span>
                  <select
                    className="r-select"
                    value={m.role}
                    onChange={(e) => roleMutation.mutate({ userId: m.id, role: e.target.value })}
                  >
                    <option value="admin">{t("role_admin")}</option>
                    <option value="member">{t("role_member")}</option>
                  </select>
                  <button
                    className="r-link-danger"
                    onClick={() => removeMutation.mutate(m.id)}
                  >
                    {t("remove")}
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="r-empty">
              <p className="r-empty-title">{t("no_team_members")}</p>
            </div>
          )}
        </div>

        {/* Invite form */}
        <div className="r-section">
          <div className="r-section-header">
            <p className="r-section-label">{t("invite_member")}</p>
          </div>
          <div className="r-invite-row">
            <input
              className="r-input"
              type="email"
              placeholder={t("member_email")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <select
              className="r-select"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              <option value="member">{t("role_member")}</option>
              <option value="admin">{t("role_admin")}</option>
            </select>
            <button
              className="r-btn-primary"
              disabled={!email || inviteMutation.isPending}
              onClick={() => inviteMutation.mutate({ email, role })}
            >
              {t("invite")}
            </button>
          </div>
          {inviteError && <p className="r-invite-error">{inviteError}</p>}
        </div>

        {/* Pending invites */}
        {invites && invites.length > 0 && (
          <div className="r-section">
            <div className="r-section-header">
              <p className="r-section-label">{t("pending_invites")}</p>
            </div>
            <div className="r-doc-list">
              {invites.map((inv) => (
                <div key={inv.id} className="r-doc-row">
                  <span className="r-doc-title">{inv.email}</span>
                  <span className={`r-pill r-pill-role-${inv.role}`}>{t(`role_${inv.role}`)}</span>
                  <span className="r-invite-link-expires">
                    {t("expires")} {new Date(inv.expires_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

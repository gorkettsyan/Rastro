import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";
import LearningHint from "../components/LearningHint";
import IntegrationsPanel from "../components/IntegrationsPanel";

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
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { user, setUser } = useAuthStore();
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

  const prefsMutation = useMutation({
    mutationFn: (data: { learning_mode: boolean }) =>
      api.patch("/auth/me/preferences", data),
    onSuccess: ({ data }) => setUser(data),
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
    <main className="r-main">
      <h2 className="r-page-title">{t("settings")}</h2>

      <LearningHint textKey="hint_settings" />

      {/* Preferences */}
      <div className="r-section">
        <div className="r-section-header">
          <p className="r-section-label">{t("preferences")}</p>
        </div>
        <div className="r-doc-list">
          <div className="r-preference-row">
            <div className="r-preference-info">
              <span className="r-preference-label">{t("learning_mode")}</span>
              <span className="r-preference-desc">{t("learning_mode_desc")}</span>
            </div>
            <button
              className={`r-toggle${user?.learning_mode ? " active" : ""}`}
              onClick={() => prefsMutation.mutate({ learning_mode: !user?.learning_mode })}
              disabled={prefsMutation.isPending}
            />
          </div>
          <div className="r-preference-row">
            <div className="r-preference-info">
              <span className="r-preference-label">{t("language_preference")}</span>
            </div>
            <div style={{ display: "flex", gap: "var(--space-xs)" }}>
              <button
                className={`r-btn-ghost${i18n.language === "en" ? " active" : ""}`}
                onClick={() => { i18n.changeLanguage("en"); localStorage.setItem("rastro_lang", "en"); }}
                style={{ padding: "6px 12px" }}
              >
                EN
              </button>
              <button
                className={`r-btn-ghost${i18n.language === "es" ? " active" : ""}`}
                onClick={() => { i18n.changeLanguage("es"); localStorage.setItem("rastro_lang", "es"); }}
                style={{ padding: "6px 12px" }}
              >
                ES
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Team roster */}
      <div className="r-section">
        <div className="r-section-header">
          <p className="r-section-label">{t("team_members")}</p>
        </div>
        {team && team.length > 0 ? (
          <div className="r-doc-list">
            {team.map((m) => (
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
                  onChange={(e) => roleMutation.mutate({ userId: m.id, role: e.target.value })}
                >
                  <option value="admin">{t("role_admin")}</option>
                  <option value="member">{t("role_member")}</option>
                </select>
                <button
                  className="r-btn-icon-danger"
                  onClick={() => removeMutation.mutate(m.id)}
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

      {/* Integrations */}
      <IntegrationsPanel />

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
  );
}

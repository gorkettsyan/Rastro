import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { useAuthStore } from "../store/auth";

interface InviteInfo {
  email: string;
  role: string;
  org_name: string | null;
  expires_at: string;
}

export default function InviteAccept() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const authToken = useAuthStore((s) => s.token);
  const [invite, setInvite] = useState<InviteInfo | null>(null);
  const [error, setError] = useState("");
  const [accepting, setAccepting] = useState(false);

  useEffect(() => {
    if (!token) return;
    api
      .get(`/team/invite/${token}`)
      .then((r) => setInvite(r.data))
      .catch((err) => setError(err.response?.data?.detail || t("error")));
  }, [token]);

  const handleAccept = async () => {
    if (!token) return;
    setAccepting(true);
    try {
      await api.post(`/team/invite/${token}/accept`);
      navigate("/");
    } catch (err: any) {
      setError(err.response?.data?.detail || t("error"));
    } finally {
      setAccepting(false);
    }
  };

  if (error) {
    return (
      <div className="r-login-page">
        <div className="r-login-card">
          <span className="r-login-logo">Rastro</span>
          <p className="r-invite-error">{error}</p>
        </div>
      </div>
    );
  }

  if (!invite) {
    return (
      <div className="r-login-page">
        <div className="r-login-card">
          <span className="r-login-logo">Rastro</span>
          <p className="r-login-tagline">{t("loading")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="r-login-page">
      <div className="r-login-card">
        <span className="r-login-logo">Rastro</span>
        <p className="r-login-tagline">
          {t("invite_join_org", { org: invite.org_name || "team" })}
        </p>
        <p style={{ fontSize: 13, color: "var(--ink-secondary)" }}>
          {invite.email} &middot; {t(`role_${invite.role}`)}
        </p>
        {authToken ? (
          <button
            className="r-btn-primary"
            onClick={handleAccept}
            disabled={accepting}
            style={{ width: "100%", justifyContent: "center" }}
          >
            {accepting ? t("loading") : t("accept_invite")}
          </button>
        ) : (
          <p className="r-login-tagline">{t("login_to_accept")}</p>
        )}
      </div>
    </div>
  );
}

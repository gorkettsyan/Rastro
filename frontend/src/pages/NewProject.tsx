import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import Header from "../components/Header";

export default function NewProject() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [clientName, setClientName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setSaving(true);
    try {
      const { data } = await api.post("/projects", {
        title: title.trim(),
        client_name: clientName.trim() || undefined,
        description: description.trim() || undefined,
      });
      navigate(`/projects/${data.id}`);
    } finally {
      setSaving(false);
    }
  };

  const inputStyle = {
    width: "100%",
    background: "var(--bg-card)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-md)",
    padding: "10px var(--space-md)",
    fontFamily: "var(--font-body)",
    fontSize: "14px",
    color: "var(--ink-primary)",
    outline: "none",
    boxSizing: "border-box" as const,
  };

  const labelStyle = {
    display: "block",
    fontSize: "12px",
    fontWeight: 500,
    color: "var(--ink-secondary)",
    marginBottom: "var(--space-xs)",
  };

  return (
    <div className="r-page">
      <Header />

      <main className="r-main" style={{ maxWidth: "560px" }}>
        <p className="r-page-title">{t("new_project")}</p>

        <form onSubmit={handleSubmit} className="r-card" style={{ display: "flex", flexDirection: "column", gap: "var(--space-lg)" }}>
          <div>
            <label style={labelStyle}>{t("project_title")} *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>{t("client_name")}</label>
            <input
              type="text"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              style={inputStyle}
            />
          </div>

          <div>
            <label style={labelStyle}>{t("description")}</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              style={{ ...inputStyle, resize: "none" }}
            />
          </div>

          <div style={{ display: "flex", gap: "var(--space-sm)", paddingTop: "var(--space-xs)" }}>
            <button
              type="button"
              onClick={() => navigate("/")}
              className="r-btn-ghost"
              style={{ flex: 1, justifyContent: "center" }}
            >
              {t("cancel")}
            </button>
            <button
              type="submit"
              disabled={saving || !title.trim()}
              className="r-btn-primary"
              style={{ flex: 1, justifyContent: "center" }}
            >
              {saving ? t("loading") : t("save")}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}

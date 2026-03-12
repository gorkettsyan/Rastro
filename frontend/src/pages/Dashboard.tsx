import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../store/auth";
import { api } from "../api/client";

interface Project {
  id: string;
  title: string;
}

interface UnassignedDoc {
  id: string;
  title: string;
  source: string;
}

export default function Dashboard() {
  const { user, setUser } = useAuthStore();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [unassigned, setUnassigned] = useState<UnassignedDoc[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const init = async () => {
      try {
        if (!user) {
          const { data } = await api.get("/auth/me");
          setUser(data);
        }
        const [projectsRes, docsRes] = await Promise.all([
          api.get("/projects"),
          api.get("/documents", { params: { unassigned: true } }).catch(() => ({ data: { items: [] } })),
        ]);
        setProjects(projectsRes.data.items);
        setUnassigned(docsRes.data.items ?? []);
      } catch {
        navigate("/login");
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  if (loading) {
    return (
      <main className="r-main">
        <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", color: "var(--ink-muted)" }}>{t("loading")}</p>
      </main>
    );
  }

  const now = new Date();
  const timeStr = now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: true });

  return (
    <main className="r-main">
      <div>
        <h1 className="r-page-title">{t("nav_home") === "Home" ? "Workspace Overview" : "Vista General"}</h1>
        <p style={{
          fontFamily: "var(--font-mono)",
          fontSize: "0.75rem",
          letterSpacing: "0.05em",
          opacity: 0.7,
          marginTop: 8,
        }}>
          {t("today")}, {timeStr}
        </p>
      </div>

      {/* Projects */}
      <div>
        <div className="r-section-header">
          <h2 className="r-section-label">{t("projects")}</h2>
          <Link to="/projects/new" className="r-btn-primary">{t("new_project")}</Link>
        </div>

        {projects.length > 0 ? (
          <div className="r-doc-list">
            {projects.map((p) => (
              <div
                key={p.id}
                className="r-doc-row"
                style={{ cursor: "pointer" }}
                onClick={() => navigate(`/projects/${p.id}`)}
              >
                <span className="r-doc-title">{p.title}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="r-empty">
            <p className="r-empty-title">{t("no_projects_title")}</p>
            <p className="r-empty-desc">{t("no_projects_desc")}</p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        textAlign: "center",
        borderTop: "1px solid var(--border-subtle)",
        paddingTop: 24,
      }}>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: "0.75rem",
          letterSpacing: "0.05em",
          color: "var(--accent)",
        }}>
          Powered by Rastro AI
        </span>
      </div>
    </main>
  );
}

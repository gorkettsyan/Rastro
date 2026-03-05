import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../store/auth";
import { api } from "../api/client";

interface Project {
  id: string;
  title: string;
  client_name: string | null;
  status: string;
  updated_at: string;
}

interface ProjectStats {
  [projectId: string]: { docCount: number; obligationCount: number; overdueCount: number };
}

function timeAgo(dateStr: string, t: (k: string, opts?: Record<string, unknown>) => string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return t("today");
  if (diffDays === 1) return t("yesterday");
  return t("days_ago", { count: diffDays });
}

export default function Projects() {
  const { user, setUser } = useAuthStore();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectStats, setProjectStats] = useState<ProjectStats>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const init = async () => {
      try {
        if (!user) {
          const { data } = await api.get("/auth/me");
          setUser(data);
        }
        const [projectsRes, obligationsRes, docsRes] = await Promise.all([
          api.get("/projects"),
          api.get("/obligations", { params: { status: "open" } }),
          api.get("/documents"),
        ]);
        setProjects(projectsRes.data.items);

        const stats: ProjectStats = {};
        const docs = docsRes.data.items || [];
        for (const doc of docs) {
          if (!doc.project_id) continue;
          if (!stats[doc.project_id]) stats[doc.project_id] = { docCount: 0, obligationCount: 0, overdueCount: 0 };
          stats[doc.project_id].docCount++;
        }
        for (const ob of (obligationsRes.data.items ?? [])) {
          if (!ob.project_id) continue;
          if (!stats[ob.project_id]) stats[ob.project_id] = { docCount: 0, obligationCount: 0, overdueCount: 0 };
          stats[ob.project_id].obligationCount++;
          if (ob.due_date) {
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const due = new Date(ob.due_date + "T00:00:00");
            if (due.getTime() < today.getTime()) {
              stats[ob.project_id].overdueCount++;
            }
          }
        }
        setProjectStats(stats);
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
        <p style={{ fontSize: "15px", color: "var(--ink-muted)" }}>{t("loading")}</p>
      </main>
    );
  }

  return (
    <main className="r-main">
      <div className="r-section">
        <div className="r-section-header">
          <p className="r-section-label">{t("projects")}</p>
          <Link to="/projects/new" className="r-btn-primary">
            + {t("new_project")}
          </Link>
        </div>

        {projects.length === 0 ? (
          <div className="r-empty">
            <span className="r-empty-icon">&#128193;</span>
            <p className="r-empty-title">{t("no_projects_title")}</p>
            <p className="r-empty-desc">{t("no_projects_desc")}</p>
          </div>
        ) : (
          <table className="r-table">
            <thead>
              <tr>
                <th>{t("project_title")}</th>
                <th>{t("client_name")}</th>
                <th>{t("documents")}</th>
                <th>{t("obligations")}</th>
                <th>{t("status")}</th>
                <th style={{ textAlign: "right" }}>{t("last_sync")}</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => {
                const stats = projectStats[p.id] || { docCount: 0, obligationCount: 0, overdueCount: 0 };
                return (
                  <tr key={p.id} onClick={() => navigate(`/projects/${p.id}`)} className="r-table-row-link">
                    <td>
                      <span className="r-table-project-name">{p.title}</span>
                    </td>
                    <td className="r-table-muted">{p.client_name || "—"}</td>
                    <td>{stats.docCount}</td>
                    <td>
                      <span>{stats.obligationCount}</span>
                      {stats.overdueCount > 0 && (
                        <span className="r-project-overdue-badge" style={{ marginLeft: 6 }}>{stats.overdueCount}</span>
                      )}
                    </td>
                    <td>
                      <span className={`r-pill r-pill-status-${p.status}`}>{t(`status_${p.status}`)}</span>
                    </td>
                    <td className="r-table-muted" style={{ textAlign: "right" }}>{timeAgo(p.updated_at, t)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}

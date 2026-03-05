import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../store/auth";
import { api } from "../api/client";

interface Project {
  id: string;
  title: string;
}

interface Obligation {
  id: string;
  description: string;
  due_date: string | null;
  obligation_type: string;
  status: string;
  document_title: string | null;
  project_id: string | null;
}

function daysLeft(dueDate: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dueDate + "T00:00:00");
  return Math.ceil((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

export default function Dashboard() {
  const { user, setUser } = useAuthStore();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [obligations, setObligations] = useState<Obligation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const init = async () => {
      try {
        if (!user) {
          const { data } = await api.get("/auth/me");
          setUser(data);
        }
        const [projectsRes, obligationsRes] = await Promise.all([
          api.get("/projects"),
          api.get("/obligations", { params: { status: "open" } }),
        ]);
        setProjects(projectsRes.data.items);
        setObligations(obligationsRes.data.items ?? []);
      } catch {
        navigate("/login");
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  const overdue = obligations
    .filter((ob) => ob.due_date && daysLeft(ob.due_date) < 0)
    .sort((a, b) => new Date(a.due_date!).getTime() - new Date(b.due_date!).getTime());

  const dueThisWeek = obligations
    .filter((ob) => ob.due_date && daysLeft(ob.due_date) >= 0 && daysLeft(ob.due_date) <= 7)
    .sort((a, b) => new Date(a.due_date!).getTime() - new Date(b.due_date!).getTime());

  const projectNameById = (id: string | null) => {
    if (!id) return null;
    const p = projects.find((p) => p.id === id);
    return p?.title || null;
  };

  if (loading) {
    return (
      <main className="r-main">
        <p style={{ fontSize: "15px", color: "var(--ink-muted)" }}>{t("loading")}</p>
      </main>
    );
  }

  return (
    <main className="r-main">
      {(overdue.length > 0 || dueThisWeek.length > 0) ? (
        <div className="r-urgent-section">
          {overdue.length > 0 && (
            <div className="r-urgent-group">
              <p className="r-urgent-label r-urgent-label--overdue">{t("overdue_items", { count: overdue.length })}</p>
              {overdue.map((ob) => (
                <Link
                  key={ob.id}
                  to={ob.project_id ? `/projects/${ob.project_id}/obligations` : "/dashboard"}
                  className="r-urgent-item r-urgent-item--overdue"
                >
                  <span className="r-pill overdue">{Math.abs(daysLeft(ob.due_date!))}d {t("overdue").toLowerCase()}</span>
                  <span className="r-urgent-desc">{ob.description}</span>
                  {ob.document_title && <span className="r-urgent-meta">{ob.document_title}</span>}
                  {ob.project_id && (
                    <span className="r-urgent-project">{projectNameById(ob.project_id)}</span>
                  )}
                </Link>
              ))}
            </div>
          )}

          {dueThisWeek.length > 0 && (
            <div className="r-urgent-group">
              <p className="r-urgent-label r-urgent-label--warning">{t("due_this_week", { count: dueThisWeek.length })}</p>
              {dueThisWeek.map((ob) => (
                <Link
                  key={ob.id}
                  to={ob.project_id ? `/projects/${ob.project_id}/obligations` : "/dashboard"}
                  className="r-urgent-item r-urgent-item--warning"
                >
                  <span className="r-pill due-soon">
                    {daysLeft(ob.due_date!) === 0
                      ? t("due_today")
                      : t("due_in_days", { count: daysLeft(ob.due_date!) })}
                  </span>
                  <span className="r-urgent-desc">{ob.description}</span>
                  {ob.document_title && <span className="r-urgent-meta">{ob.document_title}</span>}
                  {ob.project_id && (
                    <span className="r-urgent-project">{projectNameById(ob.project_id)}</span>
                  )}
                </Link>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="r-empty">
          <p className="r-empty-title">{t("no_obligations")}</p>
          <p className="r-empty-desc">{t("no_obligations_desc")}</p>
        </div>
      )}
    </main>
  );
}

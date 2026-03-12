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

interface UnassignedDoc {
  id: string;
  title: string;
  source: string;
}

function daysLeft(dueDate: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dueDate + "T00:00:00");
  return Math.ceil((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

function formatDate(d: string): string {
  const date = new Date(d + "T00:00:00");
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function statusForObligation(ob: Obligation): { label: string; className: string } {
  if (!ob.due_date) return { label: "Pending", className: "status-active" };
  const d = daysLeft(ob.due_date);
  if (d < 0) return { label: "Overdue", className: "status-overdue" };
  if (d <= 7) return { label: "Due This Week", className: "status-review" };
  return { label: "Pending", className: "status-active" };
}

export default function Dashboard() {
  const { user, setUser } = useAuthStore();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [obligations, setObligations] = useState<Obligation[]>([]);
  const [unassigned, setUnassigned] = useState<UnassignedDoc[]>([]);
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
          api.get("/documents", { params: { unassigned: true } }).catch(() => ({ data: { items: [] } })),
        ]);
        setProjects(projectsRes.data.items);
        setObligations(obligationsRes.data.items ?? []);
        setUnassigned(docsRes.data.items ?? []);
      } catch {
        navigate("/login");
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  const projectNameById = (id: string | null) => {
    if (!id) return null;
    const p = projects.find((p) => p.id === id);
    return p?.title || null;
  };

  // Sort: overdue first, then by date
  const actionRequired = obligations
    .filter((ob) => ob.due_date)
    .sort((a, b) => new Date(a.due_date!).getTime() - new Date(b.due_date!).getTime());

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

      {/* Action Required */}
      <div>
        <div className="r-section-header">
          <h2 className="r-section-label">{t("obligations")}</h2>
          <Link to="/projects/new" className="r-btn-primary">{t("new_project")}</Link>
        </div>

        {actionRequired.length > 0 ? (
          <table className="r-urgent-table">
            <thead>
              <tr>
                <th style={{ width: "40%" }}>{t("obligations")}</th>
                <th style={{ width: "25%" }}>{t("nav_projects")}</th>
                <th style={{ width: "20%" }}>{t("due_date")}</th>
                <th style={{ width: "15%" }}>{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {actionRequired.map((ob) => {
                const status = statusForObligation(ob);
                return (
                  <tr
                    key={ob.id}
                    style={{ cursor: "pointer" }}
                    onClick={() => ob.project_id && navigate(`/projects/${ob.project_id}/obligations`)}
                  >
                    <td>
                      {ob.description}
                      {ob.document_title && (
                        <div className="text-muted" style={{ opacity: 0.6, fontSize: "0.9em", fontStyle: "italic" }}>
                          {ob.document_title}
                        </div>
                      )}
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", letterSpacing: "0.05em" }}>
                      {projectNameById(ob.project_id) || "\u2014"}
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", letterSpacing: "0.05em" }}>
                      {ob.due_date ? formatDate(ob.due_date) : "\u2014"}
                    </td>
                    <td>
                      <span className={`r-pill ${status.className}`}>{status.label}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="r-empty">
            <p className="r-empty-title">{t("no_obligations")}</p>
            <p className="r-empty-desc">{t("no_obligations_desc")}</p>
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

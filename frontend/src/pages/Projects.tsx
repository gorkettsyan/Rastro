import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../store/auth";
import { api } from "../api/client";
import { toast } from "../store/toast";

interface Project {
  id: string;
  title: string;
  client_name: string | null;
  status: string;
  updated_at: string;
}

interface UnassignedDoc {
  id: string;
  title: string;
  source: string;
  indexing_status: string;
  created_at: string;
}

interface ProjectStats {
  [projectId: string]: { docCount: number };
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
  const [unassigned, setUnassigned] = useState<UnassignedDoc[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [assignProject, setAssignProject] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const init = async () => {
      try {
        if (!user) {
          const { data } = await api.get("/auth/me");
          setUser(data);
        }
        const [projectsRes, docsRes, unassignedRes] = await Promise.all([
          api.get("/projects"),
          api.get("/documents"),
          api.get("/folder-mappings/unassigned"),
        ]);
        setProjects(projectsRes.data.items);
        setUnassigned(unassignedRes.data.items);

        const stats: ProjectStats = {};
        const docs = docsRes.data.items || [];
        for (const doc of docs) {
          if (!doc.project_id) continue;
          if (!stats[doc.project_id]) stats[doc.project_id] = { docCount: 0 };
          stats[doc.project_id].docCount++;
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

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === unassigned.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(unassigned.map((d) => d.id)));
    }
  };

  const handleAssign = async () => {
    if (!assignProject || selected.size === 0) return;
    try {
      await api.post("/folder-mappings/assign-bulk", {
        project_id: assignProject,
        document_ids: Array.from(selected),
      });
      setUnassigned((prev) => prev.filter((d) => !selected.has(d.id)));
      setSelected(new Set());
      setAssignProject("");
      toast.info(t("assigned_success"));
    } catch {
      toast.error(t("error"));
    }
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
      {/* Unassigned documents inbox */}
      {unassigned.length > 0 && (
        <div className="r-section">
          <div className="r-section-header">
            <p className="r-section-label">{t("unassigned_documents")} ({unassigned.length})</p>
            {selected.size > 0 && (
              <div style={{ display: "flex", gap: "var(--space-sm)", alignItems: "center" }}>
                <span style={{ fontSize: 13, color: "var(--ink-muted)" }}>
                  {t("selected_count", { count: selected.size })}
                </span>
                <select
                  className="r-select"
                  value={assignProject}
                  onChange={(e) => setAssignProject(e.target.value)}
                  style={{ minWidth: 160 }}
                >
                  <option value="">{t("assign_to_project")}</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>{p.title}</option>
                  ))}
                </select>
                <button
                  className="r-btn-primary"
                  disabled={!assignProject}
                  onClick={handleAssign}
                >
                  {t("assign")}
                </button>
              </div>
            )}
          </div>
          <table className="r-table">
            <thead>
              <tr>
                <th style={{ width: 32 }}>
                  <input
                    type="checkbox"
                    checked={selected.size === unassigned.length && unassigned.length > 0}
                    onChange={toggleAll}
                  />
                </th>
                <th>{t("project_title")}</th>
                <th>{t("source")}</th>
                <th>{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {unassigned.map((doc) => (
                <tr key={doc.id} className="r-table-row-link" onClick={() => toggleSelect(doc.id)}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected.has(doc.id)}
                      onChange={() => toggleSelect(doc.id)}
                    />
                  </td>
                  <td><span className="r-table-project-name">{doc.title}</span></td>
                  <td className="r-table-muted">{t(`source_${doc.source}`)}</td>
                  <td>
                    <span className={`r-pill ${doc.indexing_status === "done" ? "indexed" : doc.indexing_status === "error" ? "error" : "processing"}`}>
                      {t(doc.indexing_status === "done" ? "indexed" : doc.indexing_status === "error" ? "error" : "indexing")}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Projects table */}
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
                <th>{t("status")}</th>
                <th style={{ textAlign: "right" }}>{t("last_sync")}</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => {
                const stats = projectStats[p.id] || { docCount: 0 };
                return (
                  <tr key={p.id} onClick={() => navigate(`/projects/${p.id}`)} className="r-table-row-link">
                    <td>
                      <span className="r-table-project-name">{p.title}</span>
                    </td>
                    <td className="r-table-muted">{p.client_name || "—"}</td>
                    <td>{stats.docCount}</td>
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

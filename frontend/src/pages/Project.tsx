import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { toast } from "../store/toast";
import SearchBar from "../components/SearchBar";
import SearchResult from "../components/SearchResult";
import ProjectMembers from "../components/ProjectMembers";
import { CitedChunk } from "../components/CitationCard";
import LearningHint from "../components/LearningHint";

interface ProjectData {
  id: string;
  title: string;
  client_name: string | null;
  description: string | null;
  status: string;
}

interface Document {
  id: string;
  title: string;
  source: string;
  indexing_status: string;
  chunk_count: number;
}

interface Obligation {
  id: string;
  obligation_type: string;
  description: string;
  due_date: string | null;
  status: string;
}

interface SearchState {
  query: string;
  answer: string;
  chunks: CitedChunk[];
  streaming: boolean;
}

function statusPillClass(status: string) {
  if (status === "done") return "r-pill indexed";
  if (status === "error") return "r-pill error";
  return "r-pill processing";
}

export default function Project() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [project, setProject] = useState<ProjectData | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [obligations, setObligations] = useState<Obligation[]>([]);
  const [uploading, setUploading] = useState(false);
  const [searchState, setSearchState] = useState<SearchState | null>(null);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      api.get(`/projects/${id}`),
      api.get(`/documents?project_id=${id}`),
      api.get(`/obligations?project_id=${id}&status=open`),
    ])
      .then(([p, d, o]) => {
        setProject(p.data);
        setDocuments(d.data.items);
        setObligations(o.data.items ?? []);
      })
      .catch(() => navigate("/"));
  }, [id]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !id) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    form.append("project_id", id);
    try {
      const { data } = await api.post("/documents/upload", form);
      setDocuments((prev) => [data, ...prev]);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        toast.error(t("duplicate_file"));
      } else {
        toast.error(t("error"));
      }
    } finally {
      setUploading(false);
    }
  };

  if (!project) {
    return (
      <main className="r-main">
        <p style={{ fontSize: "13px", color: "var(--ink-muted)" }}>{t("loading")}</p>
      </main>
    );
  }

  const nonGmailDocs = documents.filter((d) => d.source !== "gmail");

  return (
    <main className="r-main">
      <LearningHint textKey="hint_project" />

      {/* Project header */}
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 className="r-page-title">{project.title}</h2>
          <Link to={`/chat?project=${id}`} className="r-btn-ghost">{t("ask_about_project")}</Link>
        </div>
        {project.client_name && (
          <p style={{ fontSize: "14px", color: "var(--ink-secondary)", marginTop: "var(--space-xs)" }}>
            {project.client_name}
          </p>
        )}
        <span className={`r-pill ${project.status === "active" ? "active" : "archived"}`} style={{ marginTop: "var(--space-sm)", display: "inline-flex" }}>
          {t(`status_${project.status}`)}
        </span>
      </div>

      {/* Project-scoped search */}
      <div>
        <SearchBar projectId={id} onResult={setSearchState} />
        {searchState && (
          <SearchResult
            query={searchState.query}
            answer={searchState.answer}
            chunks={searchState.chunks}
            streaming={searchState.streaming}
          />
        )}
      </div>

      {/* Documents */}
      <div className="r-section">
        <div className="r-section-header">
          <p className="r-section-label">{t("documents")}</p>
          <label className="r-btn-primary" style={{ cursor: "pointer" }}>
            {uploading ? t("uploading") : `+ ${t("upload_document")}`}
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              style={{ display: "none" }}
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        </div>

        {nonGmailDocs.length === 0 ? (
          <div className="r-empty">
            <span className="r-empty-icon">📄</span>
            <p className="r-empty-title">{t("no_docs_title")}</p>
            <p className="r-empty-desc">{t("no_docs_desc")}</p>
          </div>
        ) : (
          <div className="r-doc-list">
            {nonGmailDocs.map((doc) => (
              <div key={doc.id} className="r-doc-row">
                <span className="r-doc-title">{doc.title}</span>
                <span className={statusPillClass(doc.indexing_status)}>
                  {t(doc.indexing_status === "done" ? "indexed"
                    : doc.indexing_status === "error" ? "error"
                    : "indexing")}
                </span>
                <button
                  className="r-btn-ghost"
                  style={{ padding: "2px 8px", fontSize: "12px", color: "var(--color-error)" }}
                  onClick={async (e) => {
                    e.stopPropagation();
                    if (!confirm(t("delete") + " " + doc.title + "?")) return;
                    try {
                      await api.delete(`/documents/${doc.id}`);
                      setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
                    } catch { toast.error(t("error")); }
                  }}
                >
                  {t("delete")}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Obligations */}
      <div className="r-section">
        <div className="r-section-header">
          <p className="r-section-label">{t("project_obligations")}</p>
          {obligations.length > 0 && (
            <Link to="/obligations" className="r-btn-ghost" style={{ padding: "6px 12px" }}>
              {t("view_all")} →
            </Link>
          )}
        </div>
        {obligations.length === 0 ? (
          <div className="r-empty">
            <p className="r-empty-title">{t("no_project_obligations")}</p>
            <p className="r-empty-desc">{t("no_project_obligations_desc")}</p>
          </div>
        ) : (
          <div className="r-doc-list">
            {obligations.slice(0, 5).map((ob) => (
              <div key={ob.id} className="r-doc-row">
                <span className={`r-pill ${ob.obligation_type === "other" ? "" : "active"}`}>
                  {t(`type_${ob.obligation_type}`)}
                </span>
                <span className="r-doc-title">{ob.description}</span>
                {ob.due_date && (
                  <span style={{ fontSize: "12px", color: "var(--ink-muted)", whiteSpace: "nowrap" }}>
                    {new Date(ob.due_date).toLocaleDateString()}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Project members */}
      {id && <ProjectMembers projectId={id} />}
    </main>
  );
}

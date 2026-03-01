import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../store/auth";
import { api } from "../api/client";
import SearchBar from "../components/SearchBar";
import SearchResult from "../components/SearchResult";
import { CitedChunk } from "../components/CitationCard";
import UpcomingObligations from "../components/UpcomingObligations";
import LearningHint from "../components/LearningHint";

interface Project {
  id: string;
  title: string;
  client_name: string | null;
  status: string;
  updated_at: string;
}

interface Document {
  id: string;
  title: string;
  source: string;
  indexing_status: string;
  project_id: string | null;
}

interface SearchState {
  query: string;
  answer: string;
  chunks: CitedChunk[];
  streaming: boolean;
}

function SourceIcon({ source }: { source: string }) {
  if (source === "drive") {
    return (
      <svg className="r-source-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M12 2L2 19h20L12 2z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (source === "gmail") {
    return (
      <svg className="r-source-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="2" y="4" width="20" height="16" rx="2" />
        <path d="M22 4L12 13 2 4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg className="r-source-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" />
      <path d="M14 2v6h6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function statusPillClass(status: string) {
  if (status === "done") return "r-pill indexed";
  if (status === "error") return "r-pill error";
  return "r-pill processing";
}

export default function Dashboard() {
  const { user, setUser } = useAuthStore();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchState, setSearchState] = useState<SearchState | null>(null);
  const [showEmails, setShowEmails] = useState(false);
  const [emailCount, setEmailCount] = useState(0);
  const [obligationCount, setObligationCount] = useState(0);
  const [memoryCount, setMemoryCount] = useState(0);

  const fetchDocuments = async (includeEmails: boolean) => {
    const params: Record<string, string> = {};
    if (includeEmails) params.include_emails = "true";
    const docsRes = await api.get("/documents", { params });
    setDocuments(docsRes.data.items);
  };

  useEffect(() => {
    const init = async () => {
      try {
        if (!user) {
          const { data } = await api.get("/auth/me");
          setUser(data);
        }
        const [projectsRes, docsRes, emailRes, obligationsRes, memoryRes] = await Promise.all([
          api.get("/projects"),
          api.get("/documents"),
          api.get("/documents", { params: { source: "gmail", include_emails: "true" } }),
          api.get("/obligations", { params: { status: "open" } }),
          api.get("/memory"),
        ]);
        setProjects(projectsRes.data.items);
        setDocuments(docsRes.data.items);
        setEmailCount(emailRes.data.total);
        setObligationCount(obligationsRes.data.items?.length ?? 0);
        setMemoryCount(memoryRes.data.items?.length ?? 0);
      } catch {
        navigate("/login");
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  const toggleEmails = async () => {
    const next = !showEmails;
    setShowEmails(next);
    await fetchDocuments(next);
  };

  return (
    <main className="r-main">
      <LearningHint textKey="hint_dashboard" />

      {/* Global search */}
      <div>
        <SearchBar onResult={setSearchState} />
        {searchState && (
          <SearchResult
            query={searchState.query}
            answer={searchState.answer}
            chunks={searchState.chunks}
            streaming={searchState.streaming}
          />
        )}
      </div>

      {!loading && (
        <div className="r-stats-row">
          <Link to="/projects" className="r-stat-card">
            <span className="r-stat-number">{documents.length}</span>
            <span className="r-stat-label">{t("stats_documents")}</span>
          </Link>
          <Link to="/obligations" className="r-stat-card">
            <span className="r-stat-number">{obligationCount}</span>
            <span className="r-stat-label">{t("stats_obligations")}</span>
          </Link>
          <Link to="/memory" className="r-stat-card">
            <span className="r-stat-number">{memoryCount}</span>
            <span className="r-stat-label">{t("stats_memories")}</span>
          </Link>
        </div>
      )}

      <UpcomingObligations />

      {/* Projects */}
      <div className="r-section">
        <div className="r-section-header">
          <p className="r-section-label">{t("projects")}</p>
          <Link to="/projects/new" className="r-btn-primary">
            + {t("new_project")}
          </Link>
        </div>

        {loading ? (
          <p style={{ fontSize: "13px", color: "var(--ink-muted)" }}>{t("loading")}</p>
        ) : projects.length === 0 ? (
          <div className="r-empty">
            <span className="r-empty-icon">📁</span>
            <p className="r-empty-title">{t("no_projects_title")}</p>
            <p className="r-empty-desc">{t("no_projects_desc")}</p>
          </div>
        ) : (
          <div className="r-project-grid">
            {projects.map((p) => (
              <Link key={p.id} to={`/projects/${p.id}`} className="r-project-card">
                <div>
                  <p className="r-project-name">{p.title}</p>
                  {p.client_name && <p className="r-project-client">{p.client_name}</p>}
                </div>
                <div className="r-project-footer">
                  <span className={`r-pill ${p.status === "active" ? "active" : "archived"}`}>
                    {t(`status_${p.status}`)}
                  </span>
                  <span className="r-project-arrow">→</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* All documents */}
      {!loading && (
        <div className="r-section">
          <div className="r-section-header">
            <p className="r-section-label">{t("all_documents")}</p>
            {emailCount > 0 && (
              <button className="r-btn-filter" onClick={toggleEmails}>
                {showEmails ? t("hide_emails") : t("show_emails")} ({emailCount})
              </button>
            )}
          </div>

          {documents.length === 0 ? (
            <div className="r-empty">
              <span className="r-empty-icon">📄</span>
              <p className="r-empty-title">{t("no_docs_title")}</p>
              <p className="r-empty-desc">{t("no_docs_desc")}</p>
            </div>
          ) : (
            <div className="r-doc-list">
              {documents.map((doc) => (
                <div key={doc.id} className="r-doc-row">
                  <SourceIcon source={doc.source} />
                  <span className="r-doc-title">{doc.title || t("untitled_document")}</span>
                  <span className={statusPillClass(doc.indexing_status)}>
                    {t(doc.indexing_status === "done" ? "indexed"
                      : doc.indexing_status === "error" ? "error"
                      : "indexing")}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </main>
  );
}

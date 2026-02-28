import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../store/auth";
import { api } from "../api/client";
import Header from "../components/Header";
import SearchBar from "../components/SearchBar";
import SearchResult from "../components/SearchResult";
import { CitedChunk } from "../components/CitationCard";

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

const SOURCE_LABEL: Record<string, string> = {
  drive: "source_drive",
  gmail: "source_gmail",
  upload: "source_upload",
};

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

  useEffect(() => {
    const init = async () => {
      try {
        if (!user) {
          const { data } = await api.get("/auth/me");
          setUser(data);
        }
        const [projectsRes, docsRes] = await Promise.all([
          api.get("/projects"),
          api.get("/documents"),
        ]);
        setProjects(projectsRes.data.items);
        setDocuments(docsRes.data.items);
      } catch {
        navigate("/login");
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  const nonGmailDocs = documents.filter((d) => d.source !== "gmail");

  return (
    <div className="r-page">
      <Header />

      <main className="r-main">
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
                    <span className="r-doc-source">{t(SOURCE_LABEL[doc.source] ?? doc.source)}</span>
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
    </div>
  );
}

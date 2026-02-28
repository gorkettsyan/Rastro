import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import MemoryBadge from "../components/MemoryBadge";
import { useAuthStore } from "../store/auth";
import { api } from "../api/client";
import LanguageSwitcher from "../components/LanguageSwitcher";
import SearchBar from "../components/SearchBar";
import SearchResult from "../components/SearchResult";
import { CitedChunk } from "../components/CitationCard";
import IntegrationsPanel from "../components/IntegrationsPanel";

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

export default function Dashboard() {
  const { user, setUser, logout } = useAuthStore();
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

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <span className="font-bold text-gray-900 text-lg">{t("app_name")}</span>
        <div className="flex items-center gap-3">
          <Link to="/chat" className="text-sm text-gray-500 hover:text-gray-900">
            {t("chat")}
          </Link>
          <MemoryBadge />
          <LanguageSwitcher />
          <span className="text-sm text-gray-500">{user?.email}</span>
          <button
            onClick={() => { logout(); navigate("/login"); }}
            className="text-sm text-gray-500 hover:text-gray-900"
          >
            {t("sign_out")}
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10">
        {/* Global search */}
        <div className="mb-8">
          <SearchBar onResult={(state) => setSearchState(state)} />
          {searchState && (
            <SearchResult
              query={searchState.query}
              answer={searchState.answer}
              chunks={searchState.chunks}
              streaming={searchState.streaming}
            />
          )}
        </div>

        <IntegrationsPanel />

        {/* Projects */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold text-gray-900">{t("projects")}</h2>
          <Link
            to="/projects/new"
            className="bg-gray-900 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-gray-800"
          >
            + {t("new_project")}
          </Link>
        </div>

        {loading ? (
          <p className="text-gray-400 text-sm">{t("loading")}</p>
        ) : projects.length === 0 ? (
          <div className="bg-white rounded-2xl border border-gray-200 p-12 text-center">
            <p className="text-gray-500 mb-2">{t("no_projects")}</p>
            <p className="text-gray-400 text-sm">{t("create_first_project")}</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {projects.map((p) => (
              <Link
                key={p.id}
                to={`/projects/${p.id}`}
                className="bg-white rounded-xl border border-gray-200 px-5 py-4 flex items-center justify-between hover:border-gray-300 transition-colors"
              >
                <div>
                  <p className="font-medium text-gray-900">{p.title}</p>
                  {p.client_name && <p className="text-sm text-gray-500 mt-0.5">{p.client_name}</p>}
                </div>
                <span className="text-xs text-gray-400 capitalize">{t(`status_${p.status}`)}</span>
              </Link>
            ))}
          </div>
        )}

        {/* All documents */}
        {!loading && (
          <div className="mt-10">
            <h2 className="text-2xl font-bold text-gray-900 mb-4">{t("all_documents")}</h2>

            {documents.filter((doc) => doc.source !== "gmail").length === 0 ? (
              <div className="bg-white rounded-2xl border border-gray-200 p-8 text-center">
                <p className="text-gray-400 text-sm">{t("no_documents")}</p>
              </div>
            ) : (
              <div className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
                {documents.filter((doc) => doc.source !== "gmail").map((doc) => (
                  <div key={doc.id} className="px-5 py-3 flex items-center justify-between">
                    <div className="min-w-0">
                      <p className="text-sm text-gray-800 truncate">{doc.title}</p>
                      {doc.project_id && (
                        <p className="text-xs text-gray-400 mt-0.5">
                          {projects.find((p) => p.id === doc.project_id)?.title ?? doc.project_id}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 ml-4 shrink-0">
                      <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                        {t(SOURCE_LABEL[doc.source] ?? doc.source)}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        doc.indexing_status === "done"
                          ? "bg-green-50 text-green-700"
                          : doc.indexing_status === "error"
                          ? "bg-red-50 text-red-700"
                          : "bg-yellow-50 text-yellow-700"
                      }`}>
                        {t(doc.indexing_status === "done" ? "indexed"
                          : doc.indexing_status === "error" ? "error"
                          : "indexing")}
                      </span>
                    </div>
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

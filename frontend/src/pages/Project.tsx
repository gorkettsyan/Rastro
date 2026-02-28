import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import LanguageSwitcher from "../components/LanguageSwitcher";
import { useAuthStore } from "../store/auth";
import SearchBar from "../components/SearchBar";
import SearchResult from "../components/SearchResult";
import { CitedChunk } from "../components/CitationCard";

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

interface SearchState {
  query: string;
  answer: string;
  chunks: CitedChunk[];
  streaming: boolean;
}

export default function Project() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { logout } = useAuthStore();
  const [project, setProject] = useState<ProjectData | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [uploading, setUploading] = useState(false);
  const [searchState, setSearchState] = useState<SearchState | null>(null);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      api.get(`/projects/${id}`),
      api.get(`/documents?project_id=${id}`),
    ])
      .then(([p, d]) => {
        setProject(p.data);
        setDocuments(d.data.items);
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
    } finally {
      setUploading(false);
    }
  };

  if (!project) return <div className="p-8 text-gray-400 text-sm">{t("loading")}</div>;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <button onClick={() => navigate("/")} className="font-bold text-gray-900 text-lg">
          Rastro
        </button>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <button onClick={() => { logout(); navigate("/login"); }} className="text-sm text-gray-500 hover:text-gray-900">
            {t("sign_out")}
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900">{project.title}</h2>
          {project.client_name && <p className="text-gray-500 mt-1">{project.client_name}</p>}
        </div>

        {/* Project-scoped search */}
        <div className="mb-6">
          <SearchBar
            projectId={id}
            onResult={(state) => setSearchState(state)}
          />
          {searchState && (
            <SearchResult
              query={searchState.query}
              answer={searchState.answer}
              chunks={searchState.chunks}
              streaming={searchState.streaming}
            />
          )}
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-5">
            <h3 className="font-semibold text-gray-900">{t("documents")}</h3>
            <label className="cursor-pointer bg-gray-900 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-gray-800">
              {uploading ? t("uploading") : `+ ${t("upload_document")}`}
              <input type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={handleUpload} disabled={uploading} />
            </label>
          </div>

          {documents.filter((doc) => doc.source !== "gmail").length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-8">{t("upload_document")}</p>
          ) : (
            <div className="divide-y divide-gray-100">
              {documents.filter((doc) => doc.source !== "gmail").map((doc) => (
                <div key={doc.id} className="py-3 flex items-center justify-between">
                  <p className="text-sm text-gray-800">{doc.title}</p>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    doc.indexing_status === "done" ? "bg-green-50 text-green-700" :
                    doc.indexing_status === "error" ? "bg-red-50 text-red-700" :
                    "bg-yellow-50 text-yellow-700"
                  }`}>
                    {t(doc.indexing_status === "done" ? "indexed" : doc.indexing_status === "error" ? "error" : "indexing")}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

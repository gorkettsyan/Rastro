import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link, useSearchParams as useURLSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { toast } from "../store/toast";
import ProjectMembers from "../components/ProjectMembers";
import SearchResult from "../components/SearchResult";
import { CitedChunk } from "../components/CitationCard";
import EntityGraph, { type GraphNode, type GraphEdge } from "../components/EntityGraph";

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

interface ClauseResult {
  document_id: string;
  title: string;
  project_id: string | null;
  found: boolean;
  clause_text: string | null;
  summary: string | null;
  confidence: "high" | "low";
  chunk_id: string | null;
  source: string;
  source_url: string | null;
}

interface MissingDoc {
  document_id: string;
  title: string;
}

type TabKey = "search" | "documents" | "clauses" | "knowledge";

const TABS: TabKey[] = ["search", "documents", "clauses", "knowledge"];

function statusPillClass(status: string) {
  if (status === "done") return "r-pill indexed";
  if (status === "error") return "r-pill error";
  return "r-pill processing";
}

export default function Project() {
  const { id, tab: tabParam } = useParams<{ id: string; tab?: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [project, setProject] = useState<ProjectData | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [activeTab, setActiveTab] = useState<TabKey>("search");

  // Resolve tab from URL param
  useEffect(() => {
    if (tabParam === "ask") {
      // Redirect old "ask" URLs to "search"
      navigate(`/projects/${id}/search`, { replace: true });
    } else if (tabParam && TABS.includes(tabParam as TabKey)) {
      setActiveTab(tabParam as TabKey);
    } else if (!tabParam) {
      setActiveTab(documents.length >= 3 ? "search" : "documents");
    }
  }, [tabParam]);

  useEffect(() => {
    if (!id) return;
    Promise.all([
      api.get(`/projects/${id}`),
      api.get(`/documents?project_id=${id}`),
    ])
      .then(([p, d]) => {
        setProject(p.data);
        setDocuments(d.data.items);
        // Set default tab based on doc count (only on initial load)
        if (!tabParam) {
          setActiveTab((d.data.items || []).length >= 3 ? "search" : "documents");
        }
      })
      .catch(() => navigate("/dashboard"));
  }, [id]);

  const switchTab = (tab: TabKey) => {
    setActiveTab(tab);
    navigate(`/projects/${id}/${tab}`, { replace: true });
  };

  if (!project) {
    return (
      <main className="r-main">
        <p style={{ fontSize: "15px", color: "var(--ink-muted)" }}>{t("loading")}</p>
      </main>
    );
  }

  return (
    <main className="r-main">
      {/* Project header */}
      <div className="r-project-header">
        <div>
          <h2 className="r-page-title">{project.title}</h2>
          {project.client_name && (
            <p className="r-project-client-subtitle">{project.client_name}</p>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="r-tabs">
        {TABS.map((tab) => (
          <button
            key={tab}
            className={`r-tab${activeTab === tab ? " r-tab--active" : ""}`}
            onClick={() => switchTab(tab)}
          >
            {t(`tab_${tab}`)}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "search" && id && <SearchTab projectId={id} />}
      {activeTab === "documents" && id && (
        <DocumentsTab projectId={id} documents={documents} setDocuments={setDocuments} />
      )}
      {activeTab === "clauses" && id && <ClausesTab projectId={id} />}
      {activeTab === "knowledge" && id && <KnowledgeTab projectId={id} />}

      {/* Folder mappings (Documents tab only) */}
      {activeTab === "documents" && id && <FolderMappingsSection projectId={id} />}

      {/* Project members (always visible at bottom) */}
      {id && activeTab === "documents" && <ProjectMembers projectId={id} />}
    </main>
  );
}

/* ─── Search Tab ─── */

function SearchTab({ projectId }: { projectId: string }) {
  const { t, i18n } = useTranslation();
  const [searchParams] = useURLSearchParams();
  const [input, setInput] = useState(searchParams.get("q") || "");
  const [searchState, setSearchState] = useState<{
    query: string;
    answer: string;
    chunks: CitedChunk[];
    streaming: boolean;
  } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const executedRef = useRef<string | null>(null);

  const executeSearch = async (query: string) => {
    if (!query.trim()) return;

    abortRef.current?.abort();
    abortRef.current = new AbortController();

    setSearchState({ query, answer: "", chunks: [], streaming: true });

    const token = localStorage.getItem("rastro_token");
    const base = import.meta.env.VITE_API_URL ?? "";
    const params = new URLSearchParams({ q: query, lang: i18n.language || "es", project_id: projectId });

    try {
      const resp = await fetch(`${base}/search/stream?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: abortRef.current.signal,
      });

      if (!resp.ok || !resp.body) {
        setSearchState({ query, answer: "", chunks: [], streaming: false });
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let answer = "";
      let chunks: CitedChunk[] = [];
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "token") {
              answer += event.content;
              setSearchState({ query, answer, chunks, streaming: true });
            } else if (event.type === "sources") {
              chunks = event.sources;
              setSearchState({ query, answer, chunks, streaming: true });
            } else if (event.type === "done") {
              setSearchState({ query, answer, chunks, streaming: false });
            }
          } catch {
            // ignore malformed line
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== "AbortError") {
        setSearchState({ query, answer: "", chunks: [], streaming: false });
      }
    }
  };

  // Auto-execute if query comes from topbar search
  useEffect(() => {
    const q = searchParams.get("q");
    if (q && q !== executedRef.current) {
      executedRef.current = q;
      setInput(q);
      executeSearch(q);
    }
  }, [searchParams]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;
    executedRef.current = trimmed;
    executeSearch(trimmed);
  };

  return (
    <div style={{ maxWidth: 800 }}>
      <form onSubmit={handleSubmit} className="r-search-wrap">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("search_in_project_placeholder")}
          className="r-search-input"
          autoFocus
        />
        <button type="submit" disabled={!input.trim()} className="r-search-btn">
          &crarr;
        </button>
      </form>

      {searchState && (
        <SearchResult
          query={searchState.query}
          answer={searchState.answer}
          chunks={searchState.chunks}
          streaming={searchState.streaming}
          showProjectLabels={false}
        />
      )}
    </div>
  );
}

/* ─── Documents Tab ─── */

function DocumentsTab({
  projectId,
  documents,
  setDocuments,
}: {
  projectId: string;
  documents: Document[];
  setDocuments: React.Dispatch<React.SetStateAction<Document[]>>;
}) {
  const { t } = useTranslation();
  const [uploading, setUploading] = useState(false);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    form.append("project_id", projectId);
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

  const nonGmailDocs = documents.filter((d) => d.source !== "gmail");

  return (
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
          <span className="r-empty-icon">&#128196;</span>
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
                style={{ padding: "2px 8px", fontSize: "14px", color: "var(--color-error)" }}
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
  );
}

/* ─── Folder Mappings ─── */

interface FolderMapping {
  id: string;
  folder_id: string;
  folder_name: string;
  project_id: string;
}

interface DriveFolder {
  id: string;
  name: string;
}

function FolderMappingsSection({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const [mappings, setMappings] = useState<FolderMapping[]>([]);
  const [folders, setFolders] = useState<DriveFolder[]>([]);
  const [selectedFolder, setSelectedFolder] = useState("");
  const [loadingFolders, setLoadingFolders] = useState(false);
  const [connected, setConnected] = useState<boolean | null>(null);

  useEffect(() => {
    api.get(`/folder-mappings?project_id=${projectId}`)
      .then(({ data }) => setMappings(data.items))
      .catch(() => {});
    api.get("/integrations/status")
      .then(({ data }) => setConnected(data.google.connected))
      .catch(() => setConnected(false));
  }, [projectId]);

  const loadFolders = async () => {
    if (folders.length > 0) return;
    setLoadingFolders(true);
    try {
      const { data } = await api.get("/folder-mappings/drive-folders");
      setFolders(data);
    } catch {
      /* empty */
    }
    setLoadingFolders(false);
  };

  const addMapping = async () => {
    const folder = folders.find((f) => f.id === selectedFolder);
    if (!folder) return;
    try {
      const { data } = await api.post("/folder-mappings", {
        project_id: projectId,
        folder_id: folder.id,
        folder_name: folder.name,
      });
      setMappings((prev) => [data, ...prev]);
      setSelectedFolder("");
    } catch (err: any) {
      if (err.response?.status === 409) {
        toast.error(t("folder_already_mapped"));
      }
    }
  };

  const removeMapping = async (id: string) => {
    await api.delete(`/folder-mappings/${id}`);
    setMappings((prev) => prev.filter((m) => m.id !== id));
  };

  return (
    <div className="r-section">
      <div className="r-section-header">
        <p className="r-section-label">{t("folder_mappings")}</p>
      </div>

      {connected === false && (
        <p style={{ fontSize: 13, color: "var(--ink-muted)" }}>
          {t("google_not_connected_folders")}
        </p>
      )}

      {connected && (
        <div className="r-invite-row" style={{ marginBottom: "var(--space-md)" }}>
          <select
            className="r-select"
            value={selectedFolder}
            onClick={loadFolders}
            onChange={(e) => setSelectedFolder(e.target.value)}
          >
            <option value="">{loadingFolders ? "..." : t("select_folder")}</option>
            {folders.map((f) => (
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </select>
          <button
            className="r-btn-primary"
            disabled={!selectedFolder}
            onClick={addMapping}
          >
            {t("add_folder_mapping")}
          </button>
        </div>
      )}

      {mappings.length === 0 ? (
        <div className="r-empty" style={{ padding: "var(--space-lg)" }}>
          <p className="r-empty-title">{t("no_folder_mappings")}</p>
          <p className="r-empty-desc">{t("no_folder_mappings_desc")}</p>
        </div>
      ) : (
        <div className="r-doc-list">
          {mappings.map((m) => (
            <div key={m.id} className="r-doc-row">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--ink-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              <span className="r-doc-title">{m.folder_name}</span>
              <button
                className="r-btn-ghost"
                style={{ padding: "2px 8px", fontSize: 14, color: "var(--color-error)" }}
                onClick={() => removeMapping(m.id)}
              >
                {t("remove")}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Clauses Tab ─── */

function ClausesTab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ClauseResult[]>([]);
  const [missing, setMissing] = useState<MissingDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [current, setCurrent] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showCompare, setShowCompare] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const abortRef = useRef<AbortController | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || loading) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setResults([]);
    setMissing([]);
    setSelected(new Set());
    setTotal(0);
    setCurrent(0);
    setLoading(true);

    try {
      const params = new URLSearchParams({ q: query.trim(), lang: localStorage.getItem("rastro_lang") || "es", project_id: projectId });
      const resp = await fetch(
        `${import.meta.env.VITE_API_URL}/clause-comparison/stream?${params}`,
        {
          headers: { Authorization: `Bearer ${localStorage.getItem("rastro_token")}` },
          signal: controller.signal,
        }
      );

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let resultCount = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split("\n");
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const event = JSON.parse(line.slice(6));
          if (event.type === "status") setTotal(event.total);
          if (event.type === "result") { resultCount++; setCurrent(resultCount); setResults((prev) => [...prev, event.data]); }
          if (event.type === "missing") setMissing((prev) => [...prev, { document_id: event.document_id, title: event.title }]);
          if (event.type === "done") setLoading(false);
        }
      }
    } catch (err: any) {
      if (err.name !== "AbortError") setLoading(false);
    }
  };

  const toggleSelect = (docId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else if (next.size < 5) next.add(docId);
      return next;
    });
  };

  const toggleExpand = (docId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId);
      else next.add(docId);
      return next;
    });
  };

  const handleExport = async (format: "docx" | "pdf") => {
    setExportOpen(false);
    const body = {
      query,
      language: localStorage.getItem("rastro_lang") || "es",
      results: results.map((r) => ({
        document_id: r.document_id, title: r.title, found: r.found,
        clause_text: r.clause_text, summary: r.summary, confidence: r.confidence,
      })),
      missing: missing.map((m) => ({ document_id: m.document_id, title: m.title })),
    };
    const resp = await fetch(
      `${import.meta.env.VITE_API_URL}/clause-comparison/export?format=${format}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("rastro_token")}` },
        body: JSON.stringify(body),
      }
    );
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `clause_comparison.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const foundResults = results.filter((r) => r.found);
  const notFoundResults = results.filter((r) => !r.found);
  const allMissing = [...missing, ...notFoundResults.map((r) => ({ document_id: r.document_id, title: r.title }))];
  const selectedResults = foundResults.filter((r) => selected.has(r.document_id));
  const colCount = selectedResults.length;

  return (
    <>
      <form onSubmit={handleSearch} style={{ display: "flex", gap: "var(--space-sm)" }}>
        <div className="r-search-wrap" style={{ flex: 1 }}>
          <input
            className="r-search-input"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("clause_query_placeholder")}
            disabled={loading}
          />
          <button type="submit" className="r-search-btn" disabled={!query.trim() || loading}>
            {loading ? "..." : "\u2192"}
          </button>
        </div>
      </form>

      {loading && total > 0 && (
        <div>
          <div className="r-progress-bar">
            <div className="r-progress-bar-fill" style={{ width: `${Math.round((current / total) * 100)}%` }} />
          </div>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            {t("comparing_progress", { current, total })}
          </p>
        </div>
      )}

      {loading && total === 0 && (
        <p style={{ fontSize: 13, color: "var(--ink-muted)" }}>{t("comparing")}</p>
      )}

      {!loading && (foundResults.length > 0 || allMissing.length > 0) && (
        <div className="r-clause-toolbar">
          <div className="r-clause-stats">
            {foundResults.length > 0 && <span>{t("clause_found_in", { count: foundResults.length })}</span>}
            {allMissing.length > 0 && <span>{t("clause_missing_in", { count: allMissing.length })}</span>}
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: "var(--space-sm)" }}>
            {selected.size >= 2 && (
              <button className="r-btn-ghost" onClick={() => setShowCompare(true)}>
                {t("compare_selected")} ({selected.size})
              </button>
            )}
            <div className="r-export-dropdown">
              <button className="r-btn-primary" onClick={() => setExportOpen(!exportOpen)}>
                {t("export_comparison")}
              </button>
              {exportOpen && (
                <div className="r-export-menu">
                  <button className="r-export-menu-item" onClick={() => handleExport("docx")}>{t("export_word")}</button>
                  <button className="r-export-menu-item" onClick={() => handleExport("pdf")}>{t("export_pdf")}</button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {foundResults.length > 0 && (
        <div className="r-section">
          <h2 className="r-section-label">{t("clause_results")}</h2>
          <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: 0 }}>{t("select_up_to_5")}</p>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-md)" }}>
            {foundResults.map((r) => (
              <div key={r.document_id} className="r-clause-card">
                <div className="r-clause-header">
                  <input type="checkbox" checked={selected.has(r.document_id)} onChange={() => toggleSelect(r.document_id)} />
                  <h3 className="r-clause-title">{r.title}</h3>
                  <span className={`r-pill ${r.confidence === "high" ? "on-track" : "due-soon"}`}>
                    {r.confidence === "high" ? t("confidence_high") : t("confidence_low")}
                  </span>
                </div>
                {r.summary && (
                  <>
                    <p className="r-clause-summary">{r.summary}</p>
                    <p className="r-clause-translated-note">{t("summary_translated")}</p>
                  </>
                )}
                {r.clause_text && (
                  <>
                    <button className="r-link-muted" style={{ marginTop: "var(--space-sm)" }} onClick={() => toggleExpand(r.document_id)}>
                      {expanded.has(r.document_id) ? "\u25B2" : "\u25BC"} {t("view_in_document")}
                    </button>
                    {expanded.has(r.document_id) && <div className="r-clause-text">{r.clause_text}</div>}
                  </>
                )}
                {r.source_url && (
                  <div className="r-clause-actions">
                    <a href={r.source_url} target="_blank" rel="noopener noreferrer" className="r-link-muted" style={{ fontSize: 12 }}>
                      {t("view_source")} &rarr;
                    </a>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && allMissing.length > 0 && (
        <div className="r-section">
          <h2 className="r-section-label">{t("clause_not_found")}</h2>
          <div className="r-card">
            <div className="r-clause-missing-list">
              {allMissing.map((m) => (
                <div key={m.document_id} className="r-clause-missing-item">{m.title}</div>
              ))}
            </div>
          </div>
        </div>
      )}

      {!loading && results.length === 0 && missing.length === 0 && query && total > 0 && (
        <div className="r-empty">
          <p className="r-empty-title">{t("no_clause_results")}</p>
        </div>
      )}

      {showCompare && selectedResults.length >= 2 && (
        <div className="r-modal-backdrop" onClick={() => setShowCompare(false)}>
          <div className="r-compare-modal" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h2 className="r-modal-title">{t("compare_selected")}</h2>
              <button className="r-btn-ghost" onClick={() => setShowCompare(false)}>{t("close")}</button>
            </div>
            <div className="r-compare-columns" style={{ gridTemplateColumns: `repeat(${colCount}, 1fr)` }}>
              {selectedResults.map((r) => (
                <div key={r.document_id} className="r-compare-column">
                  <h4 className="r-compare-column-title">{r.title}</h4>
                  <span className={`r-pill ${r.confidence === "high" ? "on-track" : "due-soon"}`} style={{ marginBottom: "var(--space-sm)", display: "inline-flex" }}>
                    {r.confidence === "high" ? t("confidence_high") : t("confidence_low")}
                  </span>
                  {r.summary && (
                    <p style={{ fontSize: 12, color: "var(--ink-secondary)", margin: "var(--space-sm) 0" }}>{r.summary}</p>
                  )}
                  <div className="r-compare-column-text">{r.clause_text || "\u2014"}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ─── Knowledge Tab ─── */

interface KnowledgeStats {
  documents_processed: number;
  total_edges: number;
}

function KnowledgeTab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [stats, setStats] = useState<KnowledgeStats>({ documents_processed: 0, total_edges: 0 });
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);

  const fetchGraph = () => {
    api
      .get("/knowledge-graph", { params: { project_id: projectId } })
      .then(({ data }) => {
        setNodes(data.nodes ?? []);
        setEdges(data.edges ?? []);
        const s = data.stats ?? {};
        setStats({
          documents_processed: s.documents_processed ?? 0,
          total_edges: s.total_edges ?? (data.edges ?? []).length,
        });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchGraph(); }, [projectId]);

  const handleScan = async () => {
    setScanning(true);
    try {
      const { data } = await api.post("/knowledge-graph/scan", null, { params: { project_id: projectId } });
      toast.info(t("scan_enqueued", { count: data.documents }));
      setTimeout(() => fetchGraph(), 8000);
    } catch { /* empty */ }
    setScanning(false);
  };

  const clausePatterns = nodes
    .filter((n) => n.type === "clause_type")
    .sort((a, b) => (b.mention_count ?? 0) - (a.mention_count ?? 0));

  if (loading) {
    return (
      <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", letterSpacing: "0.05em", color: "var(--ink-muted)" }}>
        {t("loading")}
      </p>
    );
  }

  return (
    <>
      {/* Header */}
      <div className="r-section-header">
        <h2 className="r-section-label">{t("entity_knowledge_graph")}</h2>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-md)" }}>
          <button className="r-btn-ghost" onClick={handleScan} disabled={scanning}>
            {scanning ? t("scanning") : t("scan_documents")}
          </button>
          <span className="r-graph-stats">
            {t("active_connections")}: {stats.total_edges.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Graph */}
      {nodes.length > 0 ? (
        <div className="r-graph-container">
          <EntityGraph nodes={nodes} edges={edges} />
        </div>
      ) : (
        <div className="r-empty">
          <p className="r-empty-title">{t("no_entities_title")}</p>
          <p className="r-empty-desc">{t("no_entities_desc")}</p>
        </div>
      )}

      {/* Clause patterns */}
      {clausePatterns.length > 0 && (
        <div>
          <h2 className="r-section-label">{t("recurring_clause_patterns")}</h2>
          <hr style={{ border: "none", borderTop: "1px solid var(--border-strong)", margin: "var(--space-sm) 0 var(--space-md)" }} />
          {clausePatterns.map((node) => (
            <div key={node.id} className="r-pattern-row">
              <span className="r-pattern-tag">{node.name}</span>
              <span className="r-pattern-count">{node.mention_count ?? 0} {t("occurrences")}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

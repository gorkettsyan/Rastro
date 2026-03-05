import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { toast } from "../store/toast";
import ProjectMembers from "../components/ProjectMembers";
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

interface Obligation {
  id: string;
  obligation_type: string;
  description: string;
  due_date: string | null;
  date_unresolved: boolean;
  status: string;
  source: string;
  document_title: string | null;
  document_id: string | null;
  confidence: number;
}

interface Conversation {
  id: string;
  title: string | null;
  updated_at: string;
  project_id: string | null;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: any[];
}

interface Source {
  document_id: string;
  title: string;
  source: string;
  source_url: string | null;
  score: number;
  excerpt: string;
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

type TabKey = "ask" | "documents" | "obligations" | "clauses";

const TABS: TabKey[] = ["ask", "documents", "obligations", "clauses"];

const TYPE_OPTIONS = [
  "termination_notice", "renewal_window", "payment_due",
  "option_exercise", "warranty_expiry", "other",
];

function statusPillClass(status: string) {
  if (status === "done") return "r-pill indexed";
  if (status === "error") return "r-pill error";
  return "r-pill processing";
}

function daysLeft(dueDate: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dueDate + "T00:00:00");
  return Math.ceil((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

export default function Project() {
  const { id, tab: tabParam } = useParams<{ id: string; tab?: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [project, setProject] = useState<ProjectData | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [activeTab, setActiveTab] = useState<TabKey>("ask");

  // Resolve tab from URL param
  useEffect(() => {
    if (tabParam && TABS.includes(tabParam as TabKey)) {
      setActiveTab(tabParam as TabKey);
    } else if (!tabParam) {
      // Default: Ask if docs exist, Documents otherwise
      setActiveTab(documents.length >= 3 ? "ask" : "documents");
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
          setActiveTab((d.data.items || []).length >= 3 ? "ask" : "documents");
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
      {activeTab === "ask" && id && <AskTab projectId={id} projectTitle={project.title} />}
      {activeTab === "documents" && id && (
        <DocumentsTab projectId={id} documents={documents} setDocuments={setDocuments} />
      )}
      {activeTab === "obligations" && id && <ObligationsTab projectId={id} />}
      {activeTab === "clauses" && id && <ClausesTab projectId={id} />}

      {/* Project members (always visible at bottom) */}
      {id && activeTab === "documents" && <ProjectMembers projectId={id} />}
    </main>
  );
}

/* ─── Ask Tab ─── */

function AskTab({ projectId, projectTitle }: { projectId: string; projectTitle: string }) {
  const { t } = useTranslation();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingSources, setStreamingSources] = useState<Source[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get("/chat", { params: { project_id: projectId } })
      .then(({ data }) => setConversations(data.items))
      .catch(() => {});
  }, [projectId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  const loadConversation = async (convId: string) => {
    setActiveConversationId(convId);
    try {
      const { data } = await api.get(`/chat/${convId}`);
      setMessages(data.messages);
    } catch {
      setMessages([]);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || streaming) return;
    const text = input.trim();
    setInput("");

    let convId = activeConversationId;

    if (!convId) {
      const { data } = await api.post("/chat", { first_message: text, project_id: projectId });
      convId = data.id;
      setActiveConversationId(convId);
      setConversations((prev) => [data, ...prev]);
    }

    const tempUserMsg: Message = { id: crypto.randomUUID(), role: "user", content: text, sources: [] };
    setMessages((prev) => [...prev, tempUserMsg]);
    setStreaming(true);
    setStreamingContent("");
    setStreamingSources([]);

    try {
      const resp = await fetch(
        `${import.meta.env.VITE_API_URL}/chat/${convId}/messages`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("rastro_token")}`,
          },
          body: JSON.stringify({ message: text, language: localStorage.getItem("rastro_lang") || "es" }),
        }
      );

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let fullContent = "";
      let finalSources: Source[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split("\n");
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const event = JSON.parse(line.slice(6));
          if (event.type === "token") {
            fullContent += event.content;
            setStreamingContent(fullContent);
          }
          if (event.type === "sources") {
            finalSources = event.sources;
            setStreamingSources(finalSources);
          }
          if (event.type === "done") {
            setMessages((prev) => [
              ...prev,
              { id: crypto.randomUUID(), role: "assistant", content: fullContent, sources: finalSources },
            ]);
            setStreamingContent("");
            setStreamingSources([]);
            setStreaming(false);
          }
        }
      }
    } catch {
      setStreaming(false);
    }
  };

  return (
    <div className="r-ask-tab">
      {/* Conversation history selector */}
      {conversations.length > 0 && (
        <div className="r-ask-conversations">
          <button
            className={`r-ask-conv-btn${!activeConversationId ? " active" : ""}`}
            onClick={() => { setActiveConversationId(null); setMessages([]); }}
          >
            + {t("new_conversation")}
          </button>
          {conversations.slice(0, 5).map((c) => (
            <button
              key={c.id}
              className={`r-ask-conv-btn${activeConversationId === c.id ? " active" : ""}`}
              onClick={() => loadConversation(c.id)}
            >
              {c.title || t("conversation_empty")}
            </button>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="r-ask-messages">
        {messages.length === 0 && !streaming ? (
          <div className="r-ask-empty">
            <p className="r-ask-empty-title">{t("ask_about_project_title", { project: projectTitle })}</p>
            <p className="r-ask-empty-hint">{t("ask_about_project_hint")}</p>
          </div>
        ) : (
          <>
            {messages.map((m) => (
              <div key={m.id} className={`r-ask-msg r-ask-msg--${m.role}`}>
                <div className="r-ask-msg-content">{m.content}</div>
                {m.role === "assistant" && m.sources?.length > 0 && (
                  <div className="r-ask-sources">
                    {m.sources.map((s: any, i: number) => (
                      <span key={i} className="r-ask-source-pill">
                        {s.source_type === "boe" ? "BOE" : t("source_label_project")} — {s.title}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {streaming && (
              <div className="r-ask-msg r-ask-msg--assistant">
                <div className="r-ask-msg-content">
                  {streamingContent || <span className="r-cursor" />}
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </>
        )}
      </div>

      {/* Input */}
      <div className="r-ask-input-wrap">
        <textarea
          className="r-ask-textarea"
          rows={1}
          placeholder={t("type_message")}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          disabled={streaming}
        />
        <button onClick={handleSend} disabled={!input.trim() || streaming} className="r-ask-send-btn">
          {streaming ? "\u2026" : "\u2191"}
        </button>
      </div>
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

/* ─── Obligations Tab ─── */

function ObligationsTab({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const [obligations, setObligations] = useState<Obligation[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState("open");
  const [showModal, setShowModal] = useState(false);
  const [newDesc, setNewDesc] = useState("");
  const [newType, setNewType] = useState("other");
  const [newDueDate, setNewDueDate] = useState("");
  const [scanning, setScanning] = useState(false);

  const fetchObligations = async () => {
    const params: Record<string, string> = { project_id: projectId };
    if (filterStatus) params.status = filterStatus;
    if (filterStatus === "") params.include_resolved = "true";
    try {
      const res = await api.get("/obligations", { params });
      setObligations(res.data.items);
    } catch { /* empty */ }
    setLoading(false);
  };

  useEffect(() => {
    setLoading(true);
    fetchObligations();
  }, [filterStatus, projectId]);

  const toggleStatus = async (ob: Obligation) => {
    const newStatus = ob.status === "open" ? "resolved" : "open";
    await api.patch(`/obligations/${ob.id}`, { status: newStatus });
    fetchObligations();
  };

  const deleteObligation = async (id: string) => {
    await api.delete(`/obligations/${id}`);
    fetchObligations();
  };

  const scanAll = async () => {
    setScanning(true);
    try {
      const res = await api.post("/obligations/scan", { project_id: projectId });
      setTimeout(() => fetchObligations(), 5000);
      toast.info(t("scanning_documents", { count: res.data.documents }));
    } catch { /* empty */ }
    setScanning(false);
  };

  const createObligation = async () => {
    if (!newDesc.trim()) return;
    await api.post("/obligations", {
      description: newDesc,
      obligation_type: newType,
      due_date: newDueDate || null,
      project_id: projectId,
    });
    setShowModal(false);
    setNewDesc("");
    setNewType("other");
    setNewDueDate("");
    fetchObligations();
  };

  return (
    <>
      <div className="r-section">
        <div className="r-section-header">
          <p className="r-section-label">{t("obligations")}</p>
          <div style={{ display: "flex", gap: "var(--space-sm)" }}>
            <button className="r-btn-ghost" onClick={scanAll} disabled={scanning}>
              {scanning ? t("scanning") : t("scan_documents")}
            </button>
            <button className="r-btn-primary" onClick={() => setShowModal(true)}>
              + {t("add_obligation")}
            </button>
          </div>
        </div>

        <div className="r-filter-bar">
          <select className="r-filter-select" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="">{t("status")} — All</option>
            <option value="open">{t("status_open")}</option>
            <option value="resolved">{t("status_resolved")}</option>
            <option value="snoozed">{t("status_snoozed")}</option>
          </select>
        </div>

        {loading ? (
          <p style={{ fontSize: "15px", color: "var(--ink-muted)" }}>{t("loading")}</p>
        ) : obligations.length === 0 ? (
          <div className="r-empty">
            <span className="r-empty-icon">&#128203;</span>
            <p className="r-empty-title">{t("no_project_obligations")}</p>
            <p className="r-empty-desc">{t("no_project_obligations_desc")}</p>
          </div>
        ) : (
          <div className="r-doc-list">
            {obligations.map((ob) => (
              <div key={ob.id} className={`r-obligation-row${ob.due_date && ob.status === "open" && daysLeft(ob.due_date) < 0 ? " overdue" : ob.due_date && ob.status === "open" && daysLeft(ob.due_date) <= 7 ? " warning" : ""}`}>
                {ob.due_date ? (
                  <>
                    <span className="r-obligation-meta" style={{ minWidth: 80 }}>{ob.due_date}</span>
                    <DaysLeftPill dueDate={ob.due_date} />
                  </>
                ) : (
                  <span className="r-obligation-meta" style={{ minWidth: 80 }}>&mdash;</span>
                )}
                <span className="r-pill" style={{ minWidth: 60, textAlign: "center" }}>
                  {t(`type_${ob.obligation_type}`)}
                </span>
                <span className="r-obligation-desc">{ob.description}</span>
                {ob.document_title && (
                  <span className="r-obligation-meta">{ob.document_title}</span>
                )}
                <div className="r-obligation-actions">
                  <button className="r-link-muted" onClick={() => toggleStatus(ob)} title={ob.status === "open" ? t("mark_resolved") : t("mark_open")}>
                    {ob.status === "open" ? "\u2713" : "\u21BA"}
                  </button>
                  <button className="r-link-danger" onClick={() => deleteObligation(ob.id)} title={t("delete")}>
                    &times;
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showModal && (
        <div className="r-modal-backdrop" onClick={() => setShowModal(false)}>
          <div className="r-modal" onClick={(e) => e.stopPropagation()}>
            <p className="r-modal-title">{t("new_obligation")}</p>
            <input className="r-input" placeholder={t("obligation_description")} value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
            <select className="r-filter-select" value={newType} onChange={(e) => setNewType(e.target.value)}>
              {TYPE_OPTIONS.map((tp) => (
                <option key={tp} value={tp}>{t(`type_${tp}`)}</option>
              ))}
            </select>
            <input className="r-input" type="date" value={newDueDate} onChange={(e) => setNewDueDate(e.target.value)} />
            <div className="r-modal-actions">
              <button className="r-btn-ghost" onClick={() => setShowModal(false)}>{t("cancel")}</button>
              <button className="r-btn-primary" onClick={createObligation}>{t("save")}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function DaysLeftPill({ dueDate }: { dueDate: string }) {
  const { t } = useTranslation();
  const d = daysLeft(dueDate);
  if (d < 0) return <span className="r-pill overdue">{Math.abs(d)}d {t("overdue").toLowerCase()}</span>;
  if (d === 0) return <span className="r-pill due-soon">{t("due_today")}</span>;
  if (d <= 7) return <span className="r-pill due-soon">{t("due_in_days", { count: d })}</span>;
  return <span className="r-pill on-track">{t("due_in_days", { count: d })}</span>;
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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import LearningHint from "../components/LearningHint";

interface Project {
  id: string;
  title: string;
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

export default function ClauseComparison() {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string>("");
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

  useEffect(() => {
    api.get("/projects").then(({ data }) => setProjects(data.items || [])).catch(() => {});
  }, []);

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
      const params = new URLSearchParams({ q: query.trim(), lang: localStorage.getItem("rastro_lang") || "es" });
      if (projectId) params.set("project_id", projectId);

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

          if (event.type === "status") {
            setTotal(event.total);
          }
          if (event.type === "result") {
            resultCount++;
            setCurrent(resultCount);
            setResults((prev) => [...prev, event.data]);
          }
          if (event.type === "missing") {
            setMissing((prev) => [...prev, { document_id: event.document_id, title: event.title }]);
          }
          if (event.type === "done") {
            setLoading(false);
          }
        }
      }
    } catch (err: any) {
      if (err.name !== "AbortError") setLoading(false);
    }
  };

  const toggleSelect = (docId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else if (next.size < 5) {
        next.add(docId);
      }
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
        document_id: r.document_id,
        title: r.title,
        found: r.found,
        clause_text: r.clause_text,
        summary: r.summary,
        confidence: r.confidence,
      })),
      missing: missing.map((m) => ({ document_id: m.document_id, title: m.title })),
    };

    const resp = await fetch(
      `${import.meta.env.VITE_API_URL}/clause-comparison/export?format=${format}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("rastro_token")}`,
        },
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
    <main className="r-main">
      <LearningHint textKey="hint_clause_comparison" />

        <h1 className="r-page-title">{t("clause_comparison")}</h1>

        {/* Search bar */}
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
          <select
            className="r-select"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            style={{ minWidth: 160 }}
          >
            <option value="">{t("all_projects")}</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.title}</option>
            ))}
          </select>
        </form>

        {/* Progress */}
        {loading && total > 0 && (
          <div>
            <div className="r-progress-bar">
              <div
                className="r-progress-bar-fill"
                style={{ width: `${Math.round((current / total) * 100)}%` }}
              />
            </div>
            <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
              {t("comparing_progress", { current, total })}
            </p>
          </div>
        )}

        {loading && total === 0 && (
          <p style={{ fontSize: 13, color: "var(--ink-muted)" }}>{t("comparing")}</p>
        )}

        {/* Toolbar */}
        {!loading && (foundResults.length > 0 || allMissing.length > 0) && (
          <div className="r-clause-toolbar">
            <div className="r-clause-stats">
              {foundResults.length > 0 && (
                <span>{t("clause_found_in", { count: foundResults.length })}</span>
              )}
              {allMissing.length > 0 && (
                <span>{t("clause_missing_in", { count: allMissing.length })}</span>
              )}
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
                    <button className="r-export-menu-item" onClick={() => handleExport("docx")}>
                      {t("export_word")}
                    </button>
                    <button className="r-export-menu-item" onClick={() => handleExport("pdf")}>
                      {t("export_pdf")}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Results */}
        {foundResults.length > 0 && (
          <div className="r-section">
            <h2 className="r-section-label">{t("clause_results")}</h2>
            <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: 0 }}>
              {t("select_up_to_5")}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-md)" }}>
              {foundResults.map((r) => (
                <div key={r.document_id} className="r-clause-card">
                  <div className="r-clause-header">
                    <input
                      type="checkbox"
                      checked={selected.has(r.document_id)}
                      onChange={() => toggleSelect(r.document_id)}
                    />
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
                      <button
                        className="r-link-muted"
                        style={{ marginTop: "var(--space-sm)" }}
                        onClick={() => toggleExpand(r.document_id)}
                      >
                        {expanded.has(r.document_id) ? "\u25B2" : "\u25BC"} {t("view_in_document")}
                      </button>
                      {expanded.has(r.document_id) && (
                        <div className="r-clause-text">{r.clause_text}</div>
                      )}
                    </>
                  )}
                  {r.source_url && (
                    <div className="r-clause-actions">
                      <a
                        href={r.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="r-link-muted"
                        style={{ fontSize: 12 }}
                      >
                        {t("view_source")} &rarr;
                      </a>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Missing */}
        {!loading && allMissing.length > 0 && (
          <div className="r-section">
            <h2 className="r-section-label">{t("clause_not_found")}</h2>
            <div className="r-card">
              <div className="r-clause-missing-list">
                {allMissing.map((m) => (
                  <div key={m.document_id} className="r-clause-missing-item">
                    {m.title}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && results.length === 0 && missing.length === 0 && query && total > 0 && (
          <div className="r-empty">
            <p className="r-empty-title">{t("no_clause_results")}</p>
          </div>
        )}

        {/* Side-by-side compare modal */}
        {showCompare && selectedResults.length >= 2 && (
          <div className="r-modal-backdrop" onClick={() => setShowCompare(false)}>
            <div className="r-compare-modal" onClick={(e) => e.stopPropagation()}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <h2 className="r-modal-title">{t("compare_selected")}</h2>
                <button className="r-btn-ghost" onClick={() => setShowCompare(false)}>
                  {t("close")}
                </button>
              </div>
              <div
                className="r-compare-columns"
                style={{ gridTemplateColumns: `repeat(${colCount}, 1fr)` }}
              >
                {selectedResults.map((r) => (
                  <div key={r.document_id} className="r-compare-column">
                    <h4 className="r-compare-column-title">{r.title}</h4>
                    <span className={`r-pill ${r.confidence === "high" ? "on-track" : "due-soon"}`} style={{ marginBottom: "var(--space-sm)", display: "inline-flex" }}>
                      {r.confidence === "high" ? t("confidence_high") : t("confidence_low")}
                    </span>
                    {r.summary && (
                      <p style={{ fontSize: 12, color: "var(--ink-secondary)", margin: "var(--space-sm) 0" }}>
                        {r.summary}
                      </p>
                    )}
                    <div className="r-compare-column-text">
                      {r.clause_text || "—"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
    </main>
  );
}

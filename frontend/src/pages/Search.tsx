import { useEffect, useState, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import SearchResult from "../components/SearchResult";
import { CitedChunk } from "../components/CitationCard";

interface SearchState {
  query: string;
  answer: string;
  chunks: CitedChunk[];
  streaming: boolean;
}

export default function Search() {
  const { t, i18n } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [input, setInput] = useState(searchParams.get("q") || "");
  const [searchState, setSearchState] = useState<SearchState | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const executedRef = useRef<string | null>(null);

  const projectId = searchParams.get("project_id") || undefined;

  const executeSearch = async (query: string) => {
    if (!query.trim()) return;

    abortRef.current?.abort();
    abortRef.current = new AbortController();

    setSearchState({ query, answer: "", chunks: [], streaming: true });

    const token = localStorage.getItem("rastro_token");
    const base = import.meta.env.VITE_API_URL ?? "";
    const params = new URLSearchParams({ q: query, lang: i18n.language || "es" });
    if (projectId) params.set("project_id", projectId);

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

  // Auto-search when arriving with ?q= param
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
    const params: Record<string, string> = { q: trimmed };
    if (projectId) params.project_id = projectId;
    setSearchParams(params, { replace: true });
    executeSearch(trimmed);
  };

  return (
    <main className="r-main" style={{ maxWidth: 800 }}>
      <form onSubmit={handleSubmit} className="r-search-wrap">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("search_placeholder")}
          className="r-search-input"
          autoFocus
        />
        <button type="submit" disabled={!input.trim()} className="r-search-btn">
          ↵
        </button>
      </form>

      {projectId && (
        <p style={{ fontSize: "14px", color: "var(--ink-muted)", marginTop: "var(--space-xs)" }}>
          {t("searching_in_project")}
        </p>
      )}

      {searchState && (
        <SearchResult
          query={searchState.query}
          answer={searchState.answer}
          chunks={searchState.chunks}
          streaming={searchState.streaming}
        />
      )}
    </main>
  );
}

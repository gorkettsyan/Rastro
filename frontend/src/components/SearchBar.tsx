import { useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import { CitedChunk } from "./CitationCard";

interface SearchState {
  query: string;
  answer: string;
  chunks: CitedChunk[];
  streaming: boolean;
}

interface Props {
  projectId?: string;
  onResult: (state: SearchState) => void;
}

export default function SearchBar({ projectId, onResult }: Props) {
  const { t, i18n } = useTranslation();
  const [query, setQuery] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    // Cancel any in-flight request
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    onResult({ query: trimmed, answer: "", chunks: [], streaming: true });

    const token = localStorage.getItem("rastro_token");
    const base = import.meta.env.VITE_API_URL ?? "";
    const params = new URLSearchParams({ q: trimmed, lang: i18n.language || "es" });
    if (projectId) params.set("project_id", projectId);

    try {
      const resp = await fetch(`${base}/search/stream?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: abortRef.current.signal,
      });

      if (!resp.ok || !resp.body) {
        onResult({ query: trimmed, answer: "", chunks: [], streaming: false });
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
              onResult({ query: trimmed, answer, chunks, streaming: true });
            } else if (event.type === "sources") {
              chunks = event.sources;
              onResult({ query: trimmed, answer, chunks, streaming: true });
            } else if (event.type === "done") {
              onResult({ query: trimmed, answer, chunks, streaming: false });
            }
          } catch {
            // ignore malformed line
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== "AbortError") {
        onResult({ query: trimmed, answer: "", chunks: [], streaming: false });
      }
    }
  };

  return (
    <form onSubmit={handleSubmit} className="r-search-wrap">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("search_placeholder")}
        className="r-search-input"
      />
      <button
        type="submit"
        disabled={!query.trim()}
        className="r-search-btn"
      >
        ↵
      </button>
    </form>
  );
}

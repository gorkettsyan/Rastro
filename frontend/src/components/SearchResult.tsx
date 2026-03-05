import { useState } from "react";
import { useTranslation } from "react-i18next";
import CitationCard, { CitedChunk } from "./CitationCard";
import DocumentModal from "./DocumentModal";

interface Props {
  query: string;
  answer: string;
  chunks: CitedChunk[];
  streaming: boolean;
  showProjectLabels?: boolean;
}

export default function SearchResult({ query, answer, chunks, streaming, showProjectLabels }: Props) {
  const { t } = useTranslation();
  const [expandedDocId, setExpandedDocId] = useState<string | null>(null);

  const docChunks = chunks.filter((c) => c.source_type !== "boe");
  const boeChunks = chunks.filter((c) => c.source_type === "boe");

  if (!query) return null;

  return (
    <>
      <div className="r-result-card">
        <p className="r-result-query">"{query}"</p>

        {answer ? (
          <p className="r-result-answer">
            {answer}
            {streaming && <span className="r-cursor" />}
          </p>
        ) : (
          <p className="r-result-answer" style={{ color: "var(--ink-muted)" }}>{t("searching")}</p>
        )}

        {!streaming && !answer && chunks.length === 0 && (
          <p style={{ fontSize: "14px", color: "var(--ink-muted)", marginTop: "12px" }}>{t("no_results")}</p>
        )}

        {/* Private document results — always shown first */}
        {docChunks.length > 0 && (
          <div style={{ marginTop: "var(--space-md)" }}>
            <p className="r-section-label r-source-label" style={{ marginBottom: "var(--space-sm)" }}>
              {showProjectLabels ? t("your_documents") : t("source_label_project")}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {docChunks.map((chunk, i) => (
                <CitationCard
                  key={chunk.document_id + i}
                  index={chunks.indexOf(chunk) + 1}
                  source={chunk}
                  onExpand={setExpandedDocId}
                  showAddToProject={showProjectLabels}
                  showProjectLabel={showProjectLabels}
                />
              ))}
            </div>
          </div>
        )}

        {/* Legislation and case law — separate section */}
        {boeChunks.length > 0 && (
          <div style={{ marginTop: "var(--space-lg)" }}>
            <p className="r-section-label r-source-label" style={{ marginBottom: "var(--space-sm)" }}>
              {t("legislation_section_label")}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {boeChunks.map((chunk, i) => (
                <CitationCard
                  key={chunk.document_id + i}
                  index={chunks.indexOf(chunk) + 1}
                  source={chunk}
                  onExpand={setExpandedDocId}
                />
              ))}
            </div>
            <div className="r-citation-boe-disclaimer">
              {t("boe_disclaimer_full")}
            </div>
          </div>
        )}
      </div>

      {expandedDocId && (
        <DocumentModal
          documentId={expandedDocId}
          onClose={() => setExpandedDocId(null)}
        />
      )}
    </>
  );
}

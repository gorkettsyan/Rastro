import { useState } from "react";
import { useTranslation } from "react-i18next";
import CitationCard, { CitedChunk } from "./CitationCard";
import DocumentModal from "./DocumentModal";

interface Props {
  query: string;
  answer: string;
  chunks: CitedChunk[];
  streaming: boolean;
}

export default function SearchResult({ query, answer, chunks, streaming }: Props) {
  const { t } = useTranslation();
  const [expandedDocId, setExpandedDocId] = useState<string | null>(null);

  if (!query) return null;

  return (
    <>
      <div className="bg-white rounded-2xl border border-gray-200 p-5 mt-4">
        <p className="text-xs text-gray-400 mb-3 italic">"{query}"</p>

        {answer ? (
          <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
            {answer}
            {streaming && (
              <span className="inline-block w-1.5 h-4 ml-0.5 bg-gray-400 animate-pulse align-middle" />
            )}
          </p>
        ) : (
          <p className="text-sm text-gray-400">{t("searching")}</p>
        )}

        {!streaming && answer && chunks.length === 0 && (
          <p className="text-xs text-gray-400 mt-3">{t("no_results")}</p>
        )}

        {chunks.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              {t("sources")}
            </p>
            <div className="flex flex-col gap-2">
              {chunks.map((chunk, i) => (
                <CitationCard
                  key={chunk.document_id + i}
                  index={i + 1}
                  source={chunk}
                  onExpand={setExpandedDocId}
                  showAddToProject
                />
              ))}
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

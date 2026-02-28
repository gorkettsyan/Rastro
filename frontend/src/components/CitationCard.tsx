import { useTranslation } from "react-i18next";

export interface CitedChunk {
  document_id: string;
  title: string;
  source: string;
  source_url: string | null;
  score: number;
  excerpt: string;
}

interface Props {
  chunks: CitedChunk[];
}

export default function CitationCard({ chunks }: Props) {
  const { t } = useTranslation();

  if (chunks.length === 0) return null;

  return (
    <div className="mt-4">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
        {t("sources")}
      </p>
      <div className="flex flex-col gap-2">
        {chunks.map((chunk, i) => (
          <div
            key={chunk.document_id + i}
            className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2"
          >
            <p className="text-xs font-medium text-gray-700 mb-1 truncate">
              {chunk.title}
              <span className="ml-2 text-gray-400 font-normal">
                {(chunk.score * 100).toFixed(0)}%
              </span>
            </p>
            <p className="text-xs text-gray-500 line-clamp-2">{chunk.excerpt}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

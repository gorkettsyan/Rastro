import { useState } from "react";
import CitationCard from "./CitationCard";
import DocumentModal from "./DocumentModal";

interface Source {
  document_id: string;
  title: string;
  source: string;
  source_url: string | null;
  score: number;
  excerpt: string;
}

interface Props {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  streaming?: boolean;
}

export default function MessageBubble({ role, content, sources = [], streaming }: Props) {
  const isUser = role === "user";
  const [expandedDocId, setExpandedDocId] = useState<string | null>(null);

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div className={`max-w-2xl ${isUser ? "order-2" : "order-1"}`}>
        <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? "bg-gray-900 text-white rounded-br-sm"
            : "bg-white border border-gray-200 text-gray-800 rounded-bl-sm"
        }`}>
          {content}
          {streaming && (
            <span className="inline-block w-1.5 h-4 bg-gray-400 animate-pulse ml-0.5 rounded-sm" />
          )}
        </div>
        {!isUser && sources.length > 0 && !streaming && (
          <div className="mt-2 grid gap-1.5">
            {sources.map((s, i) => (
              <CitationCard
                key={s.document_id + i}
                index={i + 1}
                source={s}
                onExpand={setExpandedDocId}
              />
            ))}
          </div>
        )}
      </div>

      {expandedDocId && (
        <DocumentModal
          documentId={expandedDocId}
          onClose={() => setExpandedDocId(null)}
        />
      )}
    </div>
  );
}

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
    <div className={`r-msg-row ${isUser ? "user" : "assistant"}`}>
      <div>
        <div className={`r-msg-bubble ${isUser ? "user" : "assistant"}`}>
          {content}
          {streaming && <span className="r-cursor" />}
        </div>
        {!isUser && sources.length > 0 && !streaming && (
          <div style={{ marginTop: "8px", display: "grid", gap: "6px" }}>
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

import AddToProjectButton from "./AddToProjectButton";

export interface CitedChunk {
  document_id: string;
  title: string;
  source: string;
  source_url: string | null;
  score: number;
  excerpt: string;
}

interface Props {
  index: number;
  source: CitedChunk;
  onExpand: (documentId: string) => void;
  showAddToProject?: boolean;
}

export default function CitationCard({ index, source, onExpand, showAddToProject }: Props) {
  return (
    <div className="r-citation" onClick={() => onExpand(source.document_id)}>
      <p className="r-citation-title">
        <span className="r-citation-index">[{index}]</span>
        {source.title}
        <span className="r-citation-score">{(source.score * 100).toFixed(0)}%</span>
      </p>
      <p className="r-citation-excerpt">{source.excerpt}</p>
      {showAddToProject && (
        <div style={{ marginTop: "8px", paddingTop: "8px", borderTop: "1px solid var(--border-subtle)" }}>
          <AddToProjectButton documentId={source.document_id} />
        </div>
      )}
    </div>
  );
}

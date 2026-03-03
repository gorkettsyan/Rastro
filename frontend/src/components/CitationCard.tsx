import { useTranslation } from "react-i18next";
import AddToProjectButton from "./AddToProjectButton";

export interface CitedChunk {
  document_id: string;
  title: string;
  source: string;
  source_url: string | null;
  score: number;
  excerpt: string;
  source_type?: string;
  law_name?: string;
  article_number?: string;
  boe_id?: string;
}

interface Props {
  index: number;
  source: CitedChunk;
  onExpand: (documentId: string) => void;
  showAddToProject?: boolean;
}

export default function CitationCard({ index, source, onExpand, showAddToProject }: Props) {
  const { t } = useTranslation();
  const isBoe = source.source_type === "boe";

  const handleClick = () => {
    if (isBoe && source.boe_id) {
      window.open(`https://www.boe.es/buscar/act.php?id=${source.boe_id}`, "_blank");
    } else {
      onExpand(source.document_id);
    }
  };

  return (
    <div className={`r-citation${isBoe ? " r-citation-boe" : ""}`} onClick={handleClick}>
      <p className="r-citation-title">
        <span className="r-citation-index">[{index}]</span>
        {source.title}
        {isBoe && <span className="r-citation-boe-badge">BOE</span>}
      </p>
      <p className="r-citation-excerpt">{source.excerpt}</p>
      {!isBoe && showAddToProject && (
        <div style={{ marginTop: "8px", paddingTop: "8px", borderTop: "1px solid var(--border-subtle)" }}>
          <AddToProjectButton documentId={source.document_id} />
        </div>
      )}
    </div>
  );
}

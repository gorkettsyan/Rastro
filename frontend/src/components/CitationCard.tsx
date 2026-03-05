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
  project_title?: string;
}

interface Props {
  index: number;
  source: CitedChunk;
  onExpand: (documentId: string) => void;
  showAddToProject?: boolean;
  showProjectLabel?: boolean;
}

export default function CitationCard({ index, source, onExpand, showAddToProject, showProjectLabel }: Props) {
  const { t } = useTranslation();
  const isBoe = source.source_type === "boe";

  const handleClick = () => {
    if (isBoe && source.boe_id) {
      window.open(`https://www.boe.es/buscar/act.php?id=${source.boe_id}`, "_blank");
    } else {
      onExpand(source.document_id);
    }
  };

  const sourceLabel = isBoe
    ? "BOE \u2014 " + t("source_label_boe_full")
    : t("source_label_project");

  return (
    <div className={`r-citation${isBoe ? " r-citation-boe" : ""}`} onClick={handleClick}>
      <div className="r-citation-header">
        <p className="r-citation-title">
          <span className="r-citation-index">[{index}]</span>
          {source.title}
        </p>
        <span className={`r-citation-source-label${isBoe ? " r-citation-source-label--boe" : ""}`}>
          {sourceLabel}
          {isBoe && (
            <svg width={10} height={10} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{ marginLeft: 4 }}>
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </span>
      </div>
      {showProjectLabel && source.project_title && (
        <p className="r-citation-project-label">{source.project_title}</p>
      )}
      <p className="r-citation-excerpt">{source.excerpt}</p>
      {!isBoe && showAddToProject && (
        <div style={{ marginTop: "8px", paddingTop: "8px", borderTop: "1px solid var(--border-subtle)" }}>
          <AddToProjectButton documentId={source.document_id} />
        </div>
      )}
    </div>
  );
}

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
    <div
      className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 cursor-pointer hover:bg-gray-100 hover:border-gray-300 transition-colors"
      onClick={() => onExpand(source.document_id)}
    >
      <p className="text-xs font-medium text-gray-700 mb-1 truncate">
        <span className="text-gray-400 mr-1">[{index}]</span>
        {source.title}
        <span className="ml-2 text-gray-400 font-normal">
          {(source.score * 100).toFixed(0)}%
        </span>
      </p>
      <p className="text-xs text-gray-500 line-clamp-2">{source.excerpt}</p>
      {showAddToProject && (
        <div className="mt-2 pt-2 border-t border-gray-200">
          <AddToProjectButton documentId={source.document_id} />
        </div>
      )}
    </div>
  );
}

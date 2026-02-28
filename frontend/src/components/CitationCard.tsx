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
}

export default function CitationCard({ index, source }: Props) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
      <p className="text-xs font-medium text-gray-700 mb-1 truncate">
        <span className="text-gray-400 mr-1">[{index}]</span>
        {source.title}
        <span className="ml-2 text-gray-400 font-normal">
          {(source.score * 100).toFixed(0)}%
        </span>
      </p>
      <p className="text-xs text-gray-500 line-clamp-2">{source.excerpt}</p>
    </div>
  );
}

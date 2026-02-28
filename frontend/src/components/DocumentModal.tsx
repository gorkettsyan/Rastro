import { useEffect, useState } from "react";
import { api } from "../api/client";

interface DocumentContent {
  id: string;
  title: string;
  source: string;
  source_url: string | null;
  content: string;
}

interface Props {
  documentId: string;
  onClose: () => void;
}

export default function DocumentModal({ documentId, onClose }: Props) {
  const [doc, setDoc] = useState<DocumentContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    setDoc(null);
    api
      .get(`/documents/${documentId}/content`)
      .then(({ data }) => setDoc(data))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [documentId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 shrink-0">
          <h2 className="font-semibold text-gray-900 truncate pr-4">
            {doc?.title ?? (loading ? "Loading…" : "Document")}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading && (
            <p className="text-sm text-gray-400">Loading document…</p>
          )}
          {error && (
            <p className="text-sm text-red-400">Failed to load document.</p>
          )}
          {doc && (
            <>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full capitalize">
                  {doc.source}
                </span>
                {doc.source_url && (
                  <a
                    href={doc.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-500 hover:underline truncate"
                  >
                    Open original ↗
                  </a>
                )}
              </div>
              <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                {doc.content}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

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
      style={{
        position: "fixed", inset: 0, zIndex: 50,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "rgba(28,25,23,0.45)",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-xl)",
          boxShadow: "var(--shadow-lg)",
          width: "100%",
          maxWidth: "680px",
          maxHeight: "80vh",
          display: "flex",
          flexDirection: "column",
          margin: "0 var(--space-md)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "var(--space-md) var(--space-lg)",
          borderBottom: "1px solid var(--border-subtle)",
          flexShrink: 0,
        }}>
          <p style={{ fontSize: "14px", fontWeight: 500, color: "var(--ink-primary)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", paddingRight: "var(--space-md)" }}>
            {doc?.title ?? (loading ? "Loading…" : "Document")}
          </p>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: "20px", color: "var(--ink-muted)", lineHeight: 1, flexShrink: 0 }}
          >
            ×
          </button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-lg)" }}>
          {loading && (
            <p style={{ fontSize: "13px", color: "var(--ink-muted)" }}>Loading document…</p>
          )}
          {error && (
            <p style={{ fontSize: "13px", color: "var(--color-error)" }}>Failed to load document.</p>
          )}
          {doc && (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)", marginBottom: "var(--space-md)" }}>
                <span className="r-doc-source r-pill">{doc.source}</span>
                {doc.source_url && (
                  <a
                    href={doc.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: "12px", color: "var(--ink-muted)", textDecoration: "none" }}
                  >
                    Open original ↗
                  </a>
                )}
              </div>
              <p style={{ fontSize: "13px", color: "var(--ink-secondary)", whiteSpace: "pre-wrap", lineHeight: 1.7, margin: 0 }}>
                {doc.content}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

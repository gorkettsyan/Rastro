import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import LearningHint from "../components/LearningHint";

interface Memory {
  id: string;
  content: string;
  source: string;
  created_at: string;
}

export default function MemoryPage() {
  const { t } = useTranslation();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [newContent, setNewContent] = useState("");
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  useEffect(() => {
    api.get("/memory").then(({ data }) => setMemories(data.items));
  }, []);

  const handleAdd = async () => {
    if (!newContent.trim()) return;
    setAdding(true);
    try {
      const { data } = await api.post("/memory", { content: newContent.trim() });
      setMemories((prev) => [data, ...prev]);
      setNewContent("");
    } finally {
      setAdding(false);
    }
  };

  const handleEdit = async (id: string) => {
    const { data } = await api.patch(`/memory/${id}`, { content: editContent });
    setMemories((prev) => prev.map((m) => (m.id === id ? data : m)));
    setEditingId(null);
  };

  const handleDelete = async (id: string) => {
    await api.delete(`/memory/${id}`);
    setMemories((prev) => prev.filter((m) => m.id !== id));
  };

  const handleDeleteAll = async () => {
    if (!confirm(t("delete_all_confirm"))) return;
    await api.delete("/memory");
    setMemories([]);
  };

  return (
    <main className="r-main" style={{ maxWidth: "680px" }}>
      <LearningHint textKey="hint_memory" />

      <div className="r-section-header" style={{ marginBottom: "var(--space-xs)" }}>
        <p className="r-page-title">🧠 {t("memories")}</p>
        {memories.length > 0 && (
          <button onClick={handleDeleteAll} className="r-link-danger">
            {t("delete_all_memories")}
          </button>
        )}
      </div>
      <p style={{ fontSize: "13px", color: "var(--ink-muted)", margin: "0 0 var(--space-xl) 0" }}>
        {t("memories_subtitle")}
      </p>

      <div className="r-memory-add" style={{ marginBottom: "var(--space-xl)" }}>
        <input
          type="text"
          className="r-memory-input"
          placeholder={t("memory_placeholder")}
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
        />
        <button
          onClick={handleAdd}
          disabled={adding || !newContent.trim()}
          className="r-btn-primary"
        >
          {t("add_memory")}
        </button>
      </div>

      {memories.length === 0 ? (
        <div className="r-empty">
          <span className="r-empty-icon">🧠</span>
          <p className="r-empty-title">{t("no_memories")}</p>
          <p className="r-empty-desc">{t("memory_empty_hint")}</p>
        </div>
      ) : (
        <div className="r-doc-list">
          {memories.map((m) => (
            <div key={m.id} className="r-doc-row">
              <span className="r-memory-source" style={{ color: "var(--ink-faint)", fontSize: "14px" }}>
                {m.source === "auto" ? "🤖" : "✏️"}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                {editingId === m.id ? (
                  <div style={{ display: "flex", gap: "var(--space-sm)" }}>
                    <input
                      className="r-memory-input"
                      style={{ flex: 1, padding: "4px 10px", fontSize: "13px" }}
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleEdit(m.id)}
                      autoFocus
                    />
                    <button onClick={() => handleEdit(m.id)} className="r-link-muted">✓</button>
                    <button onClick={() => setEditingId(null)} className="r-link-muted">✕</button>
                  </div>
                ) : (
                  <p style={{ fontSize: "13px", color: "var(--ink-primary)", margin: 0 }}>{m.content}</p>
                )}
              </div>
              {editingId !== m.id && (
                <div className="r-memory-actions">
                  <button
                    onClick={() => { setEditingId(m.id); setEditContent(m.content); }}
                    className="r-link-muted"
                  >
                    {t("edit")}
                  </button>
                  <button onClick={() => handleDelete(m.id)} className="r-link-danger">
                    {t("delete")}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}

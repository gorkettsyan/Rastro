import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import LanguageSwitcher from "../components/LanguageSwitcher";
import { useAuthStore } from "../store/auth";

interface Memory {
  id: string;
  content: string;
  source: string;
  created_at: string;
}

export default function MemoryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { logout } = useAuthStore();
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
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <button onClick={() => navigate("/")} className="font-bold text-gray-900 text-lg">
          Rastro
        </button>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <button
            onClick={() => { logout(); navigate("/login"); }}
            className="text-sm text-gray-500 hover:text-gray-900"
          >
            {t("sign_out")}
          </button>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-2xl font-bold text-gray-900">🧠 {t("memories")}</h2>
          {memories.length > 0 && (
            <button onClick={handleDeleteAll} className="text-xs text-red-400 hover:text-red-600">
              {t("delete_all_memories")}
            </button>
          )}
        </div>
        <p className="text-sm text-gray-500 mb-8">{t("memories_subtitle")}</p>

        <div className="flex gap-2 mb-8">
          <input
            type="text"
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-900"
            placeholder={t("memory_placeholder")}
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          />
          <button
            onClick={handleAdd}
            disabled={adding || !newContent.trim()}
            className="bg-gray-900 text-white text-sm font-medium px-4 py-2 rounded-lg hover:bg-gray-800 disabled:opacity-40"
          >
            {t("add_memory")}
          </button>
        </div>

        {memories.length === 0 ? (
          <div className="bg-white rounded-2xl border border-gray-200 p-12 text-center">
            <p className="text-gray-500 mb-2">{t("no_memories")}</p>
            <p className="text-gray-400 text-sm">{t("memory_empty_hint")}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {memories.map((m) => (
              <div
                key={m.id}
                className="bg-white rounded-xl border border-gray-200 px-4 py-3 flex items-start gap-3"
              >
                <span className="text-gray-300 text-xs mt-1 shrink-0">
                  {m.source === "auto" ? "🤖" : "✏️"}
                </span>
                <div className="flex-1 min-w-0">
                  {editingId === m.id ? (
                    <div className="flex gap-2">
                      <input
                        className="flex-1 border border-gray-300 rounded-lg px-2 py-1 text-sm focus:outline-none"
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleEdit(m.id)}
                        autoFocus
                      />
                      <button
                        onClick={() => handleEdit(m.id)}
                        className="text-xs text-gray-700 font-medium"
                      >
                        ✓
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="text-xs text-gray-400"
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-800">{m.content}</p>
                  )}
                </div>
                {editingId !== m.id && (
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => { setEditingId(m.id); setEditContent(m.content); }}
                      className="text-xs text-gray-400 hover:text-gray-600"
                    >
                      {t("edit")}
                    </button>
                    <button
                      onClick={() => handleDelete(m.id)}
                      className="text-xs text-red-400 hover:text-red-600"
                    >
                      {t("delete")}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

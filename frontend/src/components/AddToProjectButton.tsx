import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";

interface Project {
  id: string;
  title: string;
}

interface Props {
  documentId: string;
}

export default function AddToProjectButton({ documentId }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [open, setOpen] = useState(false);
  const [assigned, setAssigned] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get("/projects").then(({ data }) => setProjects(data.items)).catch(() => {});
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const assign = async (projectId: string, projectTitle: string) => {
    setSaving(true);
    setOpen(false);
    try {
      await api.patch(`/documents/${documentId}`, { project_id: projectId });
      setAssigned(projectTitle);
    } catch {
      // silent — user can retry
    } finally {
      setSaving(false);
    }
  };

  if (assigned) {
    return (
      <span className="text-xs text-green-600 font-medium">✓ {assigned}</span>
    );
  }

  return (
    <div ref={ref} className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={saving || projects.length === 0}
        className="text-xs text-gray-400 hover:text-gray-700 transition-colors disabled:opacity-40"
      >
        {saving ? "…" : "+ Add to project"}
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[180px]">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => assign(p.id, p.title)}
              className="w-full text-left px-3 py-2 text-xs text-gray-700 hover:bg-gray-50 truncate"
            >
              {p.title}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

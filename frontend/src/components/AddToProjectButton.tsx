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
      <span style={{ fontSize: "11px", color: "var(--color-success)", fontWeight: 500 }}>✓ {assigned}</span>
    );
  }

  return (
    <div ref={ref} style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={saving || projects.length === 0}
        style={{
          fontSize: "11px",
          color: "var(--ink-muted)",
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: 0,
          transition: "color 0.15s",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "var(--ink-secondary)")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "var(--ink-muted)")}
      >
        {saving ? "…" : "+ Add to project"}
      </button>

      {open && (
        <div style={{
          position: "absolute",
          left: 0,
          top: "100%",
          zIndex: 20,
          marginTop: "4px",
          background: "var(--bg-card)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-md)",
          boxShadow: "var(--shadow-md)",
          padding: "4px 0",
          minWidth: "180px",
        }}>
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => assign(p.id, p.title)}
              style={{
                width: "100%",
                textAlign: "left",
                padding: "7px var(--space-md)",
                fontSize: "12px",
                color: "var(--ink-secondary)",
                background: "none",
                border: "none",
                cursor: "pointer",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                transition: "background 0.12s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "none")}
            >
              {p.title}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

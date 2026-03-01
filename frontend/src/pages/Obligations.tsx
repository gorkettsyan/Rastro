import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { toast } from "../store/toast";
import LearningHint from "../components/LearningHint";

interface Obligation {
  id: string;
  description: string;
  due_date: string | null;
  date_unresolved: boolean;
  obligation_type: string;
  status: string;
  source: string;
  document_title: string | null;
  document_id: string | null;
  confidence: number;
}

interface Project {
  id: string;
  title: string;
}

const TYPE_OPTIONS = [
  "termination_notice", "renewal_window", "payment_due",
  "option_exercise", "warranty_expiry", "other",
];

function daysLeft(dueDate: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dueDate + "T00:00:00");
  return Math.ceil((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

function rowClass(ob: Obligation): string {
  if (!ob.due_date || ob.status !== "open") return "r-obligation-row";
  const d = daysLeft(ob.due_date);
  if (d < 0) return "r-obligation-row overdue";
  if (d <= 7) return "r-obligation-row warning";
  return "r-obligation-row";
}

function DaysLeftPill({ dueDate, t }: { dueDate: string; t: (k: string, opts?: object) => string }) {
  const d = daysLeft(dueDate);
  if (d < 0) return <span className="r-pill overdue">{Math.abs(d)}d {t("overdue").toLowerCase()}</span>;
  if (d === 0) return <span className="r-pill due-soon">{t("due_today")}</span>;
  if (d <= 7) return <span className="r-pill due-soon">{t("due_in_days", { count: d })}</span>;
  return <span className="r-pill on-track">{t("due_in_days", { count: d })}</span>;
}

export default function Obligations() {
  const { t } = useTranslation();
  const [obligations, setObligations] = useState<Obligation[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState("open");
  const [filterType, setFilterType] = useState("");
  const [filterProject, setFilterProject] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [showModal, setShowModal] = useState(false);

  // Modal form state
  const [newDesc, setNewDesc] = useState("");
  const [newType, setNewType] = useState("other");
  const [newDueDate, setNewDueDate] = useState("");
  const [newProjectId, setNewProjectId] = useState("");
  const [scanning, setScanning] = useState(false);

  const fetchObligations = async () => {
    const params: Record<string, string> = {};
    if (filterStatus) params.status = filterStatus;
    if (filterStatus === "") params.include_resolved = "true";
    if (filterType) params.obligation_type = filterType;
    if (filterProject) params.project_id = filterProject;
    try {
      const res = await api.get("/obligations", { params });
      setObligations(res.data.items);
    } catch { /* empty */ }
    setLoading(false);
  };

  useEffect(() => {
    api.get("/projects").then((r) => setProjects(r.data.items)).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchObligations();
  }, [filterStatus, filterType, filterProject]);

  const toggleStatus = async (ob: Obligation) => {
    const newStatus = ob.status === "open" ? "resolved" : "open";
    await api.patch(`/obligations/${ob.id}`, { status: newStatus });
    fetchObligations();
  };

  const deleteObligation = async (id: string) => {
    await api.delete(`/obligations/${id}`);
    fetchObligations();
  };

  const scanAll = async () => {
    setScanning(true);
    try {
      const res = await api.post("/obligations/scan");
      // Refetch after a short delay to let the worker process
      setTimeout(() => fetchObligations(), 5000);
      toast.info(t("scanning_documents", { count: res.data.documents }));
    } catch { /* empty */ }
    setScanning(false);
  };

  const createObligation = async () => {
    if (!newDesc.trim()) return;
    await api.post("/obligations", {
      description: newDesc,
      obligation_type: newType,
      due_date: newDueDate || null,
      project_id: newProjectId || null,
    });
    setShowModal(false);
    setNewDesc("");
    setNewType("other");
    setNewDueDate("");
    setNewProjectId("");
    fetchObligations();
  };

  return (
    <>
      <main className="r-main">
        <LearningHint textKey="hint_obligations" />

        <div className="r-section">
          <div className="r-section-header">
            <p className="r-page-title">{t("obligations")}</p>
            <div style={{ display: "flex", gap: "var(--space-sm)" }}>
              <button className="r-btn-ghost" onClick={scanAll} disabled={scanning}>
                {scanning ? t("scanning") : t("scan_documents")}
              </button>
              <button className="r-btn-primary" onClick={() => setShowModal(true)}>
                + {t("add_obligation")}
              </button>
            </div>
          </div>

          <div className="r-filter-bar">
            <select className="r-filter-select" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
              <option value="">{t("status")} — All</option>
              <option value="open">{t("status_open")}</option>
              <option value="resolved">{t("status_resolved")}</option>
              <option value="snoozed">{t("status_snoozed")}</option>
            </select>
            <select className="r-filter-select" value={filterType} onChange={(e) => setFilterType(e.target.value)}>
              <option value="">{t("obligation_type")} — All</option>
              {TYPE_OPTIONS.map((tp) => (
                <option key={tp} value={tp}>{t(`type_${tp}`)}</option>
              ))}
            </select>
            {projects.length > 0 && (
              <select className="r-filter-select" value={filterProject} onChange={(e) => setFilterProject(e.target.value)}>
                <option value="">All projects</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.title}</option>
                ))}
              </select>
            )}
          </div>

          {loading ? (
            <p style={{ fontSize: "13px", color: "var(--ink-muted)" }}>{t("loading")}</p>
          ) : obligations.length === 0 ? (
            <div className="r-empty">
              <span className="r-empty-icon">📋</span>
              <p className="r-empty-title">{t("no_obligations")}</p>
              <p className="r-empty-desc">{t("no_obligations_desc")}</p>
            </div>
          ) : (
            <div className="r-doc-list">
              {obligations.map((ob) => (
                <div key={ob.id} className={rowClass(ob)}>
                  {ob.due_date ? (
                    <>
                      <span className="r-obligation-meta" style={{ minWidth: 80 }}>
                        {ob.due_date}
                      </span>
                      <DaysLeftPill dueDate={ob.due_date} t={t} />
                    </>
                  ) : (
                    <span className="r-obligation-meta" style={{ minWidth: 80 }}>—</span>
                  )}
                  <span className="r-pill" style={{ minWidth: 60, textAlign: "center" }}>
                    {t(`type_${ob.obligation_type}`)}
                  </span>
                  <span className="r-obligation-desc">{ob.description}</span>
                  {ob.document_title && (
                    <span className="r-obligation-meta">{ob.document_title}</span>
                  )}
                  <div className="r-obligation-actions">
                    <button
                      className="r-link-muted"
                      onClick={() => toggleStatus(ob)}
                      title={ob.status === "open" ? t("mark_resolved") : t("mark_open")}
                    >
                      {ob.status === "open" ? "✓" : "↺"}
                    </button>
                    <button
                      className="r-link-danger"
                      onClick={() => deleteObligation(ob.id)}
                      title={t("delete")}
                    >
                      ×
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {showModal && (
        <div className="r-modal-backdrop" onClick={() => setShowModal(false)}>
          <div className="r-modal" onClick={(e) => e.stopPropagation()}>
            <p className="r-modal-title">{t("new_obligation")}</p>
            <input
              className="r-input"
              placeholder={t("obligation_description")}
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
            />
            <select className="r-filter-select" value={newType} onChange={(e) => setNewType(e.target.value)}>
              {TYPE_OPTIONS.map((tp) => (
                <option key={tp} value={tp}>{t(`type_${tp}`)}</option>
              ))}
            </select>
            <input
              className="r-input"
              type="date"
              value={newDueDate}
              onChange={(e) => setNewDueDate(e.target.value)}
            />
            {projects.length > 0 && (
              <select className="r-filter-select" value={newProjectId} onChange={(e) => setNewProjectId(e.target.value)}>
                <option value="">— No project —</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.title}</option>
                ))}
              </select>
            )}
            <div className="r-modal-actions">
              <button className="r-btn-ghost" onClick={() => setShowModal(false)}>{t("cancel")}</button>
              <button className="r-btn-primary" onClick={createObligation}>{t("save")}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

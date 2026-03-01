import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";

interface Obligation {
  id: string;
  description: string;
  due_date: string | null;
  obligation_type: string;
  document_title: string | null;
}

function duePill(dueDate: string, t: (k: string, opts?: object) => string) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dueDate + "T00:00:00");
  const diff = Math.ceil((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

  if (diff < 0) return <span className="r-pill overdue">{t("overdue")}</span>;
  if (diff === 0) return <span className="r-pill due-soon">{t("due_today")}</span>;
  if (diff <= 7) return <span className="r-pill due-soon">{t("due_in_days", { count: diff })}</span>;
  return <span className="r-pill on-track">{t("due_in_days", { count: diff })}</span>;
}

export default function UpcomingObligations() {
  const { t } = useTranslation();
  const [obligations, setObligations] = useState<Obligation[]>([]);

  useEffect(() => {
    api.get("/obligations/upcoming").then((res) => {
      setObligations(res.data.items);
    }).catch(() => {});
  }, []);

  if (obligations.length === 0) return null;

  return (
    <div className="r-upcoming-card">
      <div className="r-section-header">
        <p className="r-section-label">{t("upcoming_deadlines")}</p>
        <Link to="/obligations" className="r-link-muted" style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.1em" }}>
          {t("view_all")} →
        </Link>
      </div>
      {obligations.map((ob) => (
        <div key={ob.id} className="r-upcoming-item">
          {ob.due_date && duePill(ob.due_date, t)}
          <span className="r-upcoming-desc">{ob.description}</span>
          {ob.document_title && (
            <span className="r-upcoming-doc">{ob.document_title}</span>
          )}
        </div>
      ))}
    </div>
  );
}

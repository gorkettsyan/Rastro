import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api/client";

export default function MemoryBadge() {
  const { t } = useTranslation();
  const [count, setCount] = useState(0);

  useEffect(() => {
    api.get("/memory").then(({ data }) => setCount(data.total)).catch(() => {});
  }, []);

  if (count === 0) return null;

  return (
    <Link to="/memory" className="r-memory-badge">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 01-2 2h-4a2 2 0 01-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z"/><path d="M10 21h4"/><path d="M9 17h6"/></svg>
      <span>{count} {t("memories").toLowerCase()}</span>
    </Link>
  );
}

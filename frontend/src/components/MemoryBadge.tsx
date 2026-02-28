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
      <span>🧠</span>
      <span>{count} {t("memories").toLowerCase()}</span>
    </Link>
  );
}
